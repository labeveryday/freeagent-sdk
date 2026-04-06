---
name: tool-user
description: Reliable tool usage for local models
version: 1.0
---

- Use exact tool names. Do not invent names.
- Provide all required parameters with correct types (numbers not strings).
- If a tool fails, read the error and fix the specific issue.
- Do not repeat the same tool call with identical arguments.
- When you have what you need, stop calling tools and answer.
