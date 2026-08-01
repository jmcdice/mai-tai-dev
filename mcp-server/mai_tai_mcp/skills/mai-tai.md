Activate or deactivate mai-tai async collaboration mode.

## Usage

- `/mai-tai start` — Enter mai-tai mode
- `/mai-tai stop` — Exit mai-tai mode

---

## When args contains "start" (or no args)

Your VERY FIRST action must be a `chat_with_human` tool call — do NOT output any text first.
The tool call IS your response. Call it like this:

```
chat_with_human("Mai-tai mode activated! What would you like me to work on?")
```

From that point, ALL communication goes through mai-tai tools:

**`update_status`** — non-blocking, returns immediately. Use for:
- Acknowledging a task: "Got it, starting on that now..."
- Progress milestones: "Backend done, moving to frontend..."

**`chat_with_human`** — HOME BASE, blocks until the human replies. Use when:
- You finished a task ("Done! Here's what I did...")
- You need a decision before continuing
- You're ready for the next instruction

### The rule: never go idle

After completing ANY task, you MUST call `chat_with_human` to report and wait for the next
instruction. Never finish work and stop. Think of it like a phone call — you don't hang up
when you're done talking, you say "done, what's next?" and wait.

### The rule: never go quiet

While you're working, send an `update_status` **at least every ~10 minutes** — and always
*before* you block on something slow (test suites, builds, browser automation, long timeouts).

The human can't see your terminal. Silent hard work and a crashed process look identical to
them, so a long quiet stretch reads as "the bot is stuck." `update_status` is non-blocking and
costs nothing. When in doubt, ping.

```
update_status("Running the Playwright suite — ~4 min, back shortly...")
<long command>
update_status("Suite green. Now chasing the one flaky campaign test.")
```

### Correct flow

```
1. Human gives a task
2. update_status("Got it, working on X...")   ← optional, non-blocking
3. Do the work
4. update_status("Still going — run 3 of 6...")  ← every ~10 min, REQUIRED for long work
5. chat_with_human("Done! Here's what I did. What's next?")  ← REQUIRED
6. Wait for response → repeat
```

---

## When args contains "stop"

1. Stop using mai-tai tools immediately
2. Resume normal terminal conversation (respond directly as text)
3. Give a brief summary of what you accomplished in mai-tai mode
