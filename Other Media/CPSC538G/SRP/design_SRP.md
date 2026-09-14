# SRP Design

 I kept EDF as the base scheduler, then added  SRP on top of it in a few specific places:

- task metadata
- admission control
- scheduler task selection
- semaphore/resource handling
- optional stack sharing


## Main design choices

### 1. Integrating SRP w/ EDF

The tasks still carry EDF timing fields like deadline and period, the ready list is still ordered by absolute deadline, and task creation still goes through the EDF creation path

Then SRP changes who is *eligible* to run when the scheduler looks at that EDF list.

So the flow is more like:

- EDF says who is earliest
- SRP says whether that task is actually allowed to start right now


### 2. Use deadline-derived preemption levels instead of inventing a separate numbering scheme

For SRP, every task needs a preemption level and every resource needs a ceiling. I decided to derive those from the EDF relative deadlines instead of making the user manually assign a bunch of levels.

That is what `xSRPComputePreemptionLevel()` does:

In practice, it just maps smaller relative deadlines to larger SRP levels by subtracting the deadline from `portMAX_DELAY`.

So shorter relative deadline means higher SRP preemption level.

This just makes it easier to translate between EDF and SRP; more urgent EDF tasks naturally end up with stronger SRP preemption levels, and resource ceilings can be registered using the same deadline-style values the rest of the demo already uses

### 3. Put SRP resource state in one small kernel-side table

Instead of hiding SRP state inside the queue/semaphore internals, I kept a separate table of SRP resources:

- semaphore handle
- ceiling
- owner
- locked state
- blocking time

That made the SRP logic easier to read and easier to debug. When something goes wrong, it is pretty obvious where the live SRP state is:

- `srpResources[]`
- `systemCeiling`
- `ceilingStack[]`

It also meant I could add SRP through wrapper APIs like `vSRPRegisterSemaphore()`, `xSemaphoreTake_SRP()`, and `xSemaphoreGive_SRP()` without needing to rewrite the normal semaphore internal functionality.

### 4. Use wrapper semaphores instead of changing every normal semaphore path

I kept SRP resource access explicit:

- register the resource with `vSRPRegisterSemaphore()`
- take it with `xSemaphoreTake_SRP()`
- release it with `xSemaphoreGive_SRP()`

So normal semaphores still behave like ordinary semaphores, and only resources that are meant to participate in SRP go through the ceiling logic

This felt safer and more straightfoward than trying to make *every* semaphore in the kernel magically behave like an SRP resource.

### 5. Use one global live ceiling plus a ceiling stack

At runtime, SRP really cares about one thing: what is the current system ceiling?

So I kept:

- one `systemCeiling`
- one `ceilingStack[]`

The live ceiling changes on `xSemaphoreTake_SRP()`, and then on `xSemaphoreGive_SRP()` it gets popped back to whatever was there before.

That stack is important because it keeps nested resource usage sane. Without it, the code would not know what ceiling to return to after a nested critical section ends.

### 6. Make admission control use SRP blocking, not just normal EDF demand
The admission test now includes SRP blocking as well as the normal EDF utilization bound.

The task-creation path computes a blocking term for each task, and the feasibility check adds one blocking hit into each PDA window.


### 7. Stack sharing

Stack sharing is behind `configUSE_STACK_SHARING`, so there are two SRP modes:

- SRP without shared stacks
- SRP with shared stacks

This made debugging much easier. If basic SRP scheduling was wrong, I could turn stack sharing off and not be unsure whether I was figuring out a context-copy bug instead of a scheduling bug.

For stack-sharing, tasks at the same SRP preemption level share one live execution stack, but each task still has its own saved stack-image buffer. On a context switch:

- outgoing task saves the current shared stack image
- incoming task restores its saved image back into that shared stack

This isn't the most memory-optimal way to do stack sharing, but it is a lot simpler and safer than trying to do a more granular implementation.

### How the stack-sharing gains are measured

The stack report output to the serial monitor measures a few different things at once:

- `Private actual total` means "what if every task had its own live execution stack"
- `SRP model shared total` means "if tasks at the same preemption level shared one live stack, what would the idealized live-stack total be"
- `Actual unique range total` means "how many unique live stack ranges are actually present in this implementation"
- `Context buffer total` is all the private saved stack-image buffers added together

The summary lines are just differences between those totals:

- `Theoretical SRP savings = Private actual total - SRP model shared total`
- `Actual implemented savings = Private actual total - Actual unique range total`
- `Net memory savings = Private actual total - Actual unique range total - Context buffer total`

So in a nutshell. report separates savings in **live execution-stack ranges** vs savings in **overall RAM**

That is why the shared-stack version can show really good "actual implemented savings", but still show weak or zero "net memory savings". The live stacks are shared, but each task still keeps its own saved stack-image buffer that uses up the net memory.

You'll see examples of the actual stack report in `testing_SRP.md`

### How kernel decides stack size for shared tasks

For the stack report, the kernel doesn't just assume the stack is `uxStackDepth * sizeof(StackType_t)` and call it a day. It looks at the task's recorded stack addresses:

- `pxStack`
- `pxEndOfStack`,

then normalizes those into a low address and a high address, and measures the range as:

 `(stackEnd - stackStart) + sizeof(StackType_t)`.

So the report is using the actual aligned stack range the task ended up with.

This is also why the numbers can look a little funny (i.e. a task that was created with a nominal `256 * 4 = 1024` byte stack can still show up as `1020` bytes in the report, because the live stack range is being measured from the aligned addresses, not just from the original request size.)

### How same-level tasks are counted

For the **theoretical** shared model, the kernel groups tasks by SRP preemption level. Then for each preemption level, it only counts one live stack, and it uses the **largest** stack size seen among the tasks at that level, so all the tasks that might use it at some point can fit.

For the **actual** implementation totals, the kernel looks for unique live stack ranges instead. So if two tasks are really pointing at the same shared execution stack, that range only gets counted once in `Actual unique range total`.

### A small implementation sidenote

The saved context buffers are counted differently from the live execution-stack ranges. The live stack range is measured from the actual aligned addresses, but the saved context buffer size is stored separately as the full requested copy-buffer size.

So it's normal for the report to show something like, with neither being wrong, just different:

- live shared stack range: `1020 bytes`
- per-task saved context buffer: `1024 bytes`


## Feasibility tests used

### What the kernel actually uses

For SRP-enabled builds, the real feasibility test is basically processor demand analysis plus the SRP blocking term

There are two SRP-specific parts in the PDA code.

First, the search horizon includes the maximum blocking term in the task set;  without SRP, `tmax` is based on execution demand, but with SRP, `tmax` is expanded by the maximum blocking term in the task set.

Then each demand window adds one blocking hit:

- without SRP, the code just checks whether processor demand by itself exceeds `t`
- with SRP, it adds one worst-case blocking hit for that window before making the pass/fail check

That "one blocking hit" choice is intentional. Under SRP, the model is that a job can be blocked at most once before it starts, so the kernel uses the maximum blocking term, not a sum of a bunch of resource holds.

### Where the blocking term comes from

The per-task blocking term is computed from the registered SRP resources:

- scan the registered SRP resources
- keep only the ones whose ceiling is high enough to block the task
- use the maximum blocking time among those resources as that task's blocking term

So the resource registration step is not just bookkeeping for runtime locking. It also make the feasibility test work.

