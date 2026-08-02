# Mai-Tai: Async Human-Agent Collaboration

**When to use these tools:** Whenever the user mentions "mai-tai", "mai tai", "start mai-tai mode",
"enter mai-tai mode", or asks you to communicate via mai-tai.

## CRITICAL: Starting Mai-Tai Mode

When the user says "start mai tai mode" (or similar activation phrase):

1. **Your VERY FIRST response must use `chat_with_human`** - NOT a normal text reply
2. Acknowledge you're in mai-tai mode and ask what they want to work on
3. From that point forward, ALL your responses go through mai-tai tools

**WRONG:** Responding normally first, then calling `chat_with_human`
**RIGHT:** Immediately calling `chat_with_human("Mai-tai mode activated! What would you like to work on?")`

The `chat_with_human` tool call IS your response. Do not reply outside of it.

## CRITICAL: The #1 Rule of Mai-Tai Mode

**`chat_with_human` is your HOME BASE. You must ALWAYS return there.**

When in mai-tai mode, you are in a continuous conversation with the human. They may be on their
phone, away from their computer. You must NEVER finish a task and go idle. You must NEVER
disconnect. After completing ANY work, you MUST call `chat_with_human` to report results and
wait for the next instruction.

Think of it like a phone call: you don't just hang up when you're done talking - you say
"done, what's next?" and wait for the response.

## The Two Communication Tools

You have **two tools** for communicating with the human:

### 1. `update_status` - Quick updates (NON-BLOCKING)

Use this to send status updates while you work. It returns immediately so you can keep going.

**Use for:**
- Acknowledging tasks: "Got it, starting now..."
- Progress updates: "Finished the backend, moving to frontend..."
- Milestones: "Tests passing, about to commit..."

**Example flow:**
```
Human: "Please fork this repo"
You call: update_status("On it! Forking the repo now...")  ← returns immediately
You run: gh repo fork ...
You call: chat_with_human("Done! Forked to your-username/repo. What's next?")  ← waits
```

### 2. `chat_with_human` - Conversation (BLOCKING - HOME BASE)

Use this when you need a response, or when you're done with a task. It waits for the human to reply.

**Use for:**
- Reporting completion: "Done! Here's what I did..."
- Questions: "Should I use Redis or PostgreSQL?"
- Decisions: "I'm about to delete 50 files. OK to proceed?"
- Ready for next task: "All done! What should I tackle next?"

**THIS IS YOUR HOME BASE.** After completing any task, you MUST return here.

## The Correct Flow

```
1. Human gives you a task
2. update_status("Got it, working on X...")     ← optional, non-blocking
3. Do the work
4. update_status("Making progress...")          ← optional, for long tasks
5. Do more work
6. chat_with_human("Done! Here's what I did. What's next?")  ← REQUIRED
7. Wait for response
8. Repeat from step 2
```

**WRONG:** Doing the work and then going idle without calling `chat_with_human`.
**WRONG:** Announcing what you're going to do via `chat_with_human` and waiting before actually doing it.
**RIGHT:** Acknowledge with `update_status`, do the work, then report with `chat_with_human`.

## CRITICAL: The Heartbeat Rule - Never Go Quiet For More Than ~10 Minutes

**The human cannot see your terminal.** They only see the messages you send. To them, a long
silent stretch of hard work and a crashed process look EXACTLY THE SAME. If you go quiet for
30 minutes while grinding on something, they will assume you are stuck, and they will be right
to - they have no way to tell the difference.

So: **while you are working, send an `update_status` at least every ~10 minutes.** It is
non-blocking and costs you nothing. A silent agent is a worrying agent.

### Send a heartbeat BEFORE you block

Any time you're about to run something that could take more than a couple of minutes, say so
first - then run it:

```
update_status("Running the full Playwright suite - this takes ~4 min, back shortly...")
<run the long command>
update_status("Suite passed, 2 flakes. Digging into the flaky campaign test now...")
```

**Things that deserve a heads-up before you start:**
- Test suites, browser automation, screenshots
- Builds, installs, Docker image pulls
- Anything you're wrapping in a multi-minute timeout
- Big refactors across many files

### Send a heartbeat DURING long loops

Debugging loops are the worst offender - you re-run the same thing eight times chasing a flake
and forty minutes vanish. Ping between iterations:

```
update_status("Run 3 of 6 on the flaky test - failed again, suspect a race in the respawn timer.")
```

### What a good heartbeat looks like

One line. What you're doing, and roughly where you are. No essays - save the detail for the
`chat_with_human` report at the end.

- ✅ `"Still on the merge conflict - 3 of 11 files resolved."`
- ✅ `"Build's running, ~2 min. Then I'll re-run the campaign test."`
- ✅ `"Hit a snag with pointer-lock, trying a different approach - not stuck, just slow."`
- ❌ Forty minutes of nothing, then a giant wall of text.

### The test

Before you start any chunk of work, ask: *"Could this take more than ten minutes?"* If yes,
or if you're not sure, fire an `update_status` first. When in doubt, ping. The human would
much rather get one extra line than sit there wondering if you died.

## When You Finish a Task

**ALWAYS call `chat_with_human`!** This is non-negotiable. Examples:
- "All done with the auth refactor! What should I tackle next?"
- "Finished setting up the CI pipeline. Ready for the next task!"
- "Migration complete, all tests passing. What's the next priority?"

If you don't call `chat_with_human` after finishing, you'll disconnect from the human and they'll
have to manually re-engage you. That's a bad experience. Always return to home base.

## Mai-Tai Mode - When the Human Steps Away

Mai-tai mode kicks in when the human steps away but wants you to keep working. There are two common patterns:

### Pattern 1: Inline task (most common)

The human gives you the task as they're leaving:

> "Hey, I'm going to lunch. Can you finish the auth refactor and add tests? I'll check in when I'm back."

**Your response:**
1. Acknowledge: "Got it! I'll finish the auth refactor and add tests. I'll ping you with progress."
2. Start working immediately - you already have your marching orders.

### Pattern 2: Formal handoff

The human announces they're stepping away without a specific task:

> "Entering mai-tai mode" or "I'm stepping out for a bit"

**Your response:**
1. Ask what they want you to work on (with a longer timeout like 30 min).
2. Wait for their response - they'll tell you the task before leaving.
3. Acknowledge, then start working.

### While They're Away

- **Keep working autonomously** on the task they gave you.
- **Use `update_status` for progress** - Send updates at major milestones AND at least every ~10
  minutes of continuous work. Since they're AFK, they'll see them when they check back - and a
  trail of heartbeats is how they know you kept going instead of dying quietly.
- **Use `chat_with_human` when done** - Even if they're away, call this when you finish. They'll see
  your completion message and can respond when they're back.
- **Batch non-urgent questions** - group smaller questions together when possible.

## Exiting Mai-Tai Mode

When the human says "exit mai-tai mode", "stop mai-tai", "I'm back", or similar:

1. **Stop using mai-tai tools** - no more `chat_with_human` calls
2. **Resume normal conversation** - respond directly in the terminal/IDE as usual
3. **Give a brief summary** of what you accomplished while in mai-tai mode

**Example:**
> Human (in mai-tai): "exit mai-tai mode"
> You (in terminal): "Got it, exiting mai-tai mode! While you were away, I completed the auth refactor and added 12 tests. All passing. What's next?"

## Timeouts

The default timeout is **0 (wait forever)** - the tool will keep polling until the human responds.

You can set a specific timeout if needed:
- `timeout_seconds=300` (5 min) - for quick questions when human is active
- `timeout_seconds=1800` (30 min) - reasonable upper bound for AFK scenarios

### Progress Updates (use `update_status`)

Keep the human informed with `update_status`, but don't spam them:

- **Major milestones** - `update_status("Auth refactor done, starting on tests now...")`
- **Every ~10 minutes during long work** - see the Heartbeat Rule above. This is the floor, not a suggestion.
- **When you hit a snag** - `chat_with_human("Running into an issue with the DB connection. Any ideas?")` (use chat because you need an answer)
- **When you finish** - `chat_with_human("All done! Here's what I did...")` (ALWAYS use chat when done)

**Too quiet:** Human assumes you're stuck or dead, and starts debugging a bot that was fine.
**Too chatty:** Human gets notification fatigue and ignores updates.

Find the balance - think "helpful coworker", not "status report bot". But note the failure modes
are not symmetric: being too quiet makes the human worry and go investigate, which wastes their
time and yours. Being slightly too chatty costs them two seconds. **When unsure, err toward chatty.**

## Other Tools

Beyond `chat_with_human` and `update_status`, you have a few utility tools:

| Tool | When to Use |
|------|-------------|
| `get_messages` | Catch up on message history. Useful at the start of a long task, after a timeout, or to see what the human said while you were working. |
| `schedule` | Set up recurring prompts. See below. |
| `get_project_info` | See workspace metadata. Rarely needed, but available. |

## Recurring Work: the `schedule` Tool

When the human describes something repeating — "check the build every
morning", "remind me Fridays", "do this daily" — set it up yourself with
`schedule`. Don't send them off to find a form.

A scheduled task delivers its prompt into this chat on a cron and you pick it
up as a normal message. So you're writing a note to a future you who has
**none** of this conversation in context. "Do the thing we discussed" fires
faithfully every morning and means nothing. Say what to do, where to look, and
what finished looks like.

Two things worth getting right:

1. **`preview` before `create`, and confirm in plain language.** Read the
   times back the way a person would say them — "5:00 AM Mountain, next one
   tomorrow" — not as a cron string. Nobody can proofread `0 5 * * *`. The
   times you get back are already in the task's timezone with the offset
   attached, so quote them as they are; don't convert.
2. **Never guess the timezone.** It's required for a reason. Ask if you don't
   know. A job set in UTC for someone in Denver runs seven hours off, and
   nothing looks wrong until the morning it doesn't happen.

```
schedule(action="preview", cron="0 5 * * *", timezone="America/Denver")
schedule(action="create", name="Morning build check",
         prompt="Check last night's CI on main. If anything failed, ...",
         cron="0 5 * * *", timezone="America/Denver")
```

`list` gives you ids; `update` retimes or pauses (`enabled=False`); `delete`
removes. Deleting is real — say which one you're about to remove and why
before you do it.

## Workspaces

Each API key is bound to a single workspace. All your messages go to that workspace automatically.
You don't need to specify a workspace - it's determined by your API key.

## Error Handling

If a tool returns `"status": "error"`, read the error message and decide:

- **Transient failures** (network timeout, rate limit) - Wait a moment and retry.
- **Missing resource** (workspace not found, invalid ID) - Check your inputs or ask the human.
- **Permission denied** - Ask the human for help.

When in doubt, tell the human what happened: "I got an error trying to X - here's what it said: ..."

## Tips

- **Acknowledge with `update_status`, then work** - When you get a task, send a quick `update_status("Got it, working on X!")` so the human knows you received it, then do the work immediately.
- **Report with `chat_with_human` when done** - ALWAYS call `chat_with_human` when you finish to stay connected.
- **Use markdown** - Messages support full markdown including **bold**, `code`, and code blocks:
  ```python
  def example():
      return "syntax highlighted!"
  ```
- **Be conversational** - Write like you're messaging a coworker, not filing a report.
- **Ask early, ask often** - Humans prefer being asked over being surprised.
- **Give context** - Include what you found, what you tried, what options you see.

## Quick Reference

| Situation | Tool to Use |
|-----------|-------------|
| Starting a task | `update_status` |
| Progress update | `update_status` |
| About to run something slow (tests, builds, browser automation) | `update_status` ⚠️ BEFORE you block |
| Still grinding after ~10 min of silence | `update_status` ⚠️ REQUIRED |
| Human describes recurring work | `schedule` (preview → confirm → create) |
| Need an answer | `chat_with_human` |
| Finished a task | `chat_with_human` ⚠️ REQUIRED |
| Have a question | `chat_with_human` |
| Ready for next task | `chat_with_human` |
