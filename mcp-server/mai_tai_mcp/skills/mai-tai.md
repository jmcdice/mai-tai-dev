Activate or deactivate mai-tai async collaboration mode.

## Usage

- `/mai-tai start` — Enter mai-tai mode (fresh session)
- `/mai-tai resume` — Re-enter mai-tai mode after a restart, without greeting
- `/mai-tai stop` — Exit mai-tai mode

---

## When args contains "start" (or no args)

Do NOT output any text first — your tool calls ARE your response.

1. Call `memory("context")` to load your persistent memory (MEMORY.md, the last
   two days of journal, lessons learned). Read it before you act.
2. Call `chat_with_human` to greet:

```
memory(action="context")
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

---

## When args contains "resume"

Your session was rotated or restarted by the supervisor. The human did not ask
for this and should not have to see it. Do NOT greet, do NOT announce that you
are back, do NOT summarize what you were doing.

```
memory(action="context")
wait_for_human()
```

`wait_for_human` blocks exactly like `chat_with_human` but posts nothing. If the
human sent messages while you were down, they come back immediately; otherwise
you wait silently until they say something. Then carry on as normal — from that
point the flow is identical to `start`.

If your conversation history came back with you (the supervisor resumes the
previous session), you already know what you were doing. If it did not, the
memory context is your recall — and `search_history` will find anything older.

---

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

### The rule: write it down before you forget it

Your session gets rotated roughly once a day, and one day it will be rotated
mid-task. Memory is what survives that; your context is not.

- **`journal`** — task state, decisions, what's in flight. Journal when you
  finish a chunk of work, when you make a decision worth remembering, and
  before any long-running task. Today's and yesterday's entries load at the
  next session start.
- **`memory`** — durable facts, preferences, and decisions that still matter
  next week. 2200-char cap, so consolidate rather than pile on. Loaded at
  EVERY session start.
- **`search_history`** — full-text search over everything ever said in this
  workspace. Search before asking the human to repeat themselves.

Rule of thumb: if the human would be annoyed to have to tell you again, it goes
in `memory`. If your future self would be lost without it, it goes in `journal`.

### Correct flow

```
1. Human gives a task
2. update_status("Got it, working on X...")   ← optional, non-blocking
3. Do the work
4. update_status("Still going — run 3 of 6...")  ← every ~10 min, REQUIRED for long work
5. journal("Finished X; Y still open because Z")  ← before you report
6. chat_with_human("Done! Here's what I did. What's next?")  ← REQUIRED
7. Wait for response → repeat
```

---

## When args contains "stop"

1. Stop using mai-tai tools immediately
2. Resume normal terminal conversation (respond directly as text)
3. Give a brief summary of what you accomplished in mai-tai mode
