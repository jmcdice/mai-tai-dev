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

### Correct flow

```
1. Human gives a task
2. update_status("Got it, working on X...")   ← optional, non-blocking
3. Do the work
4. chat_with_human("Done! Here's what I did. What's next?")  ← REQUIRED
5. Wait for response → repeat
```

---

## When args contains "stop"

1. Stop using mai-tai tools immediately
2. Resume normal terminal conversation (respond directly as text)
3. Give a brief summary of what you accomplished in mai-tai mode
