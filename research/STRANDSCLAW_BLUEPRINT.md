# StrandsClaw: The Local-First, Secure-by-Default AI Agent Platform

## Built on AWS Strands Agents | Powered by Ollama | Security That Doesn't Require a PhD

**Repo Name**: `strandsclaw`
**Tagline**: "OpenClaw proved the demand. We fixed the problems."
**Package**: `pip install strandsclaw`
**One-liner**: The open-source AI agent that runs on YOUR machine, with YOUR models, under YOUR control.

---

# PART 1: OpenClaw Architecture — Complete Technical Teardown

## What OpenClaw Actually Is

OpenClaw is NOT a coding assistant. It is a **full-spectrum personal AI agent platform** — a 24/7 always-on daemon that connects to 24+ messaging channels (WhatsApp, Telegram, Discord, Slack, Signal, iMessage, etc.) and automates your entire digital life: email triage, browser control, file management, smart home, scheduling, coding, and multi-agent orchestration. Coding is just one "skill" among hundreds.

It has exploded to **345,000+ GitHub stars** in under five months, making it the fastest-growing open-source project in history. It's written in TypeScript (430,000+ LOC) atop the Pi agent framework, running as a single Node.js gateway process.

## The Four-Layer Architecture

OpenClaw's core insight: a personal AI assistant is fundamentally a **message router with an agent loop bolted on**.

### Layer 1: Gateway (Connection & Auth)

The entire system runs as a single long-lived Node.js process binding to `127.0.0.1:18789`. This process manages everything: channel connections, session state, agent execution, model calls, tool dispatch, memory persistence, and a WebSocket control plane.

Key design decisions:
- **Single process** — no microservices, no external workers, no Redis
- **WebSocket multiplexing** — all client communication over one connection
- **Scope-based authorization** — four levels: `operator.admin`, `operator.write`, `operator.read`, `operator.approvals`
- **Wire protocol** — WebSocket text frames with JSON payloads, TypeBox schemas compiled to JSON Schema, codegen to Swift/Kotlin for native clients
- **Configuration** — Zod-to-JSON-Schema pipeline with hot-reload via chokidar

### Layer 2: Execution (Agent Loop & Concurrency)

The execution layer serializes tasks through a **Lane Queue system**:
- Each session gets its own queue (prevents tool/session races)
- Global throttling capped at `maxConcurrent: 4` agents by default
- Parallelism is opt-in through dedicated lanes for cron and subagent work
- Pure TypeScript promises — no external workers or threads

This is OpenClaw's **core reliability innovation**. It consciously optimizes for personal/small-team use over horizontal scaling.

### Layer 3: Integration (Channel Normalization)

Messages from 24+ platforms are normalized into a unified `InboundEnvelope` format. Each channel adapter handles platform-specific quirks (message limits, media types, authentication) and converts to the common format. Channels include:
- WhatsApp, Telegram, Discord, Slack, Signal, iMessage
- SMS, Email (IMAP/SMTP)
- Web UI, CLI, API
- Matrix, Nostr, IRC
- And more via plugins

### Layer 4: Intelligence (Agent Behavior)

OpenClaw does NOT implement its own agent runtime. It wraps the **Pi agent framework** by Mario Zechner:
- `@mariozechner/pi-ai` — universal LLM interface
- `@mariozechner/pi-agent-core` — agent loop with tool execution
- `@mariozechner/pi-coding-agent` — file tools, JSONL session persistence, context compaction, skills system

**Critical architectural insight**: OpenClaw is a gateway and orchestration layer wrapping an external agent framework, NOT a monolithic agent built from scratch.

## How A Single Agent Turn Executes

A single turn flows through eight named stages:

```
1. SESSION RESOLUTION
   └─ Determines sessionKey based on channel, user, scope mode
      (per-peer, per-channel-peer, etc.)

2. WORKSPACE SETUP
   └─ Ensures bootstrap files exist:
      IDENTITY.md, SKILLS.md, SOUL.md

3. MODEL SELECTION
   └─ Resolves primary model + fallback chain
   └─ Checks allowlists and per-agent overrides

4. SYSTEM PROMPT BUILDING (~9,600 tokens baseline)
   └─ Assembles: identity + skills + memory + tools
   └─ Into a single system message

5. TOOL POLICY RESOLUTION
   └─ Cascading filter chain:
      global → provider → agent → group → sandbox
   └─ Deny ALWAYS wins

6. MODEL PROMPTING
   └─ Calls provider API with streaming
   └─ Handles rate limits and fallback chains

7. TOOL EXECUTION LOOP
   └─ Runs returned tool calls
   └─ Feeds results back to model
   └─ Repeats until final text response

8. SESSION PERSISTENCE
   └─ Appends to JSONL transcript
   └─ Updates token usage counters
```

The key functions:
- `runEmbeddedPiAgent()` in `src/agents/pi-embedded-runner/run.ts` — handles concurrency, model resolution, auth profile iteration
- `runAgentTurnWithFallback()` — wraps model invocation in retry loop handling rate limits, compaction failures, session resets

### Error Recovery: Four-Layer Context Protection

1. **Pre-flight context window guard** — checks token count before sending
2. **Tool result sanitization** — cleans/truncates large tool outputs
3. **In-memory context pruning** — lossless trimming of old tool results
4. **LLM-based compaction** — when overflow occurs, distills session into memory files

Critical safety mechanism: before compaction, OpenClaw injects a silent "agentic turn" prompting the model to save important context to disk, preventing memory loss.

## The Skills System

Skills are directories containing a `SKILL.md` file with YAML frontmatter (name, description, runtime requirements) and Markdown instructions.

```
skills/
├── coding-agent/
│   └── SKILL.md          # YAML frontmatter + markdown instructions
├── browser-control/
│   └── SKILL.md
├── email-triage/
│   └── SKILL.md
└── custom-skill/
    └── SKILL.md
```

Three-tier precedence: **workspace skills → global skills → bundled skills**

The agent can **self-author new skills** during conversation — ask it to automate something, and it writes a new SKILL.md. ClawHub hosts 5,700+ community skills.

### The Coding Agent Skill Specifically

The coding-agent skill runs external coding agents with PTY support:

```bash
bash pty:true workdir:~/project background:true command:"codex --yolo exec 'Build REST API'"
```

Wake triggers provide notification when background agents finish:
```bash
openclaw system event --text "Done" --mode now
```

It can spawn Codex, Claude Code, or Aider as background processes and report results via any messaging channel.

## The Memory Architecture

Memory uses **plain Markdown files in the workspace**, not a hidden database. Eight boot files load at every session start:

| File | Purpose |
|------|---------|
| `SOUL.md` | Personality, values, behavioral guidelines |
| `AGENTS.md` | Operational rules and agent behavior |
| `USER.md` | User preferences and personal context |
| `TOOLS.md` | Tool configuration and usage patterns |
| `IDENTITY.md` | Agent identity and name |
| `HEARTBEAT.md` | Proactive task definitions |
| `BOOTSTRAP.md` | Initialization instructions |
| `MEMORY.md` | Long-term facts and accumulated knowledge |

Daily logs go to `memory/YYYY-MM-DD.md` — today and yesterday auto-load. Everything else is retrieved on-demand through **hybrid search**:
- **70% weight**: Vector similarity (via sqlite-vec)
- **30% weight**: BM25 keyword matching (via SQLite FTS5)
- Markdown chunks to ~400 tokens with 80-token overlap
- All stored in SQLite — zero external dependencies

## LLM Provider Integration

Built-in providers via the Pi AI abstraction layer:

| Provider | Models |
|----------|--------|
| Anthropic | Claude 4, Claude 3.5 Sonnet, Haiku |
| OpenAI | GPT-4o, GPT-4.1, o3, o4-mini |
| Google | Gemini 2.5 Pro/Flash |
| AWS Bedrock | All Bedrock models |
| Ollama | Any local model |
| Groq | Fast inference models |
| xAI | Grok |
| OpenRouter | 100+ models |
| DeepSeek | DeepSeek V3/R1 |
| Mistral | Mistral Large/Medium |

### Ollama Integration (Two Modes)

1. **Native API mode** (recommended): Uses `/api/chat` with full streaming + tool calling simultaneously, auto-discovery via `/api/tags` and `/api/show`
2. **OpenAI-compatible mode** (legacy): Uses `/v1` but tool calling is unreliable

Model switching: CLI command, mid-conversation `/model` slash command (instant, no context loss), or per-agent config override.

**Two-tier model system**: `primary` model for general work, `thinking` model for complex reasoning, with automatic escalation.

## Security Model (The Achilles Heel)

### The Trust Model
- Assumes a single trusted operator per gateway
- NOT a multi-tenant system
- Plugins/extensions are part of the trusted computing base

### Default State: Wide Open
- **By default**: Can execute ANY shell command — no restrictions, no allowlist, no approval
- Exec approvals and tool policy chains exist but must be manually configured
- Sandbox mode uses Docker containers but setup is complex

### The Security Track Record
- **CVE-2026-25253** (CVSS 8.8): One-click RCE via WebSocket origin bypass
- **Cisco audit**: Top-ranked ClawHub skill was performing data exfiltration — 9 vulnerabilities, 2 critical
- **Koi Security**: 341 malicious skills out of 2,857 audited (11.9%)
- **ArXiv study**: 26.1% of 31,000 analyzed skills had at least one vulnerability
- **Chinese government**: Banned OpenClaw from government systems
- **Microsoft Defender team**: "Running OpenClaw is not simply a configuration choice. It is a trust decision."

## How OpenClaw Compares to Everything Else

| Tool | Type | Stars | Model Lock | Local LLMs | Scope | Price |
|------|------|-------|-----------|------------|-------|-------|
| **OpenClaw** | Personal AI Agent | 345k | None | Yes (Ollama) | Everything | Free + API costs |
| **Cursor** | IDE Coding | N/A | Multi | No | Code only | $20/mo |
| **Claude Code** | CLI Coding | ~50k | Claude only | No | Code only | API costs |
| **Copilot** | IDE Autocomplete | N/A | GPT | No | Code only | $10/mo |
| **Aider** | CLI Coding | ~30k | Multi | Yes | Code only | Free + API |
| **Devin** | Autonomous Dev | N/A | Proprietary | No | Code only | $500+/mo |
| **Windsurf** | IDE Coding | N/A | Multi | No | Code only | $15/mo |

OpenClaw's unique advantages: multi-channel presence, always-on autonomous operation, persistent cross-session memory, life automation beyond code, 5,700+ skill ecosystem.

OpenClaw's weaknesses: 30-60 minute setup, critical security vulnerabilities, cost unpredictability, weaker deep code understanding than purpose-built tools.

---

# PART 2: StrandsClaw — The Strands Agents Rebuild Plan

## Design Philosophy

**Three pillars that define everything:**

1. **Local-First**: Ollama with GPU acceleration is the DEFAULT experience, not an afterthought. Zero API cost out of the box. Cloud providers are optional upgrades.

2. **Secure-by-Default**: Mandatory sandboxing, tool allowlists, and cryptographic skill verification. You should NOT need to be a security expert to safely run an AI agent.

3. **Dead Simple**: `pip install strandsclaw && strandsclaw init` works in under 60 seconds. One command. One config file. Done.

## Architecture Overview

StrandsClaw replaces OpenClaw's TypeScript/Pi framework stack with a pure Python architecture built on AWS Strands Agents. Instead of wrapping an external agent framework, Strands IS the framework.

```
┌─────────────────────────────────────────────────────┐
│                   StrandsClaw                        │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   Channels   │  │   Security   │  │   Memory   │ │
│  │  CLI / Web   │  │  Sandbox +   │  │  Markdown  │ │
│  │  API / MCP   │  │  Allowlists  │  │  + SQLite  │ │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                 │                │         │
│  ┌──────▼─────────────────▼────────────────▼──────┐ │
│  │              Strands Agent Core                 │ │
│  │                                                 │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │ │
│  │  │  Agent    │  │  Tools   │  │  Hooks &     │ │ │
│  │  │  Loop     │  │  System  │  │  Callbacks   │ │ │
│  │  └──────────┘  └──────────┘  └──────────────┘ │ │
│  │                                                 │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │ │
│  │  │ Sessions │  │ Convo    │  │  Multi-Agent  │ │ │
│  │  │ Manager  │  │ Manager  │  │  Orchestrator │ │ │
│  │  └──────────┘  └──────────┘  └──────────────┘ │ │
│  └─────────────────────┬───────────────────────────┘ │
│                        │                             │
│  ┌─────────────────────▼───────────────────────────┐ │
│  │              Model Provider Layer                │ │
│  │                                                  │ │
│  │  Ollama (default)  │  Bedrock  │  Anthropic     │ │
│  │  + GPU auto-detect │  OpenAI   │  Any OpenAI-   │ │
│  │  + Model auto-pull │  Groq     │  compatible    │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## Project Structure

```
strandsclaw/
├── pyproject.toml                  # Package config, pip install strandsclaw
├── strandsclaw/
│   ├── __init__.py
│   ├── cli.py                      # CLI entry point (click)
│   ├── core/
│   │   ├── agent.py                # StrandsClawAgent (wraps strands.Agent)
│   │   ├── config.py               # Pydantic config with YAML/TOML support
│   │   ├── lane_queue.py           # Per-session task serialization
│   │   └── bootstrap.py            # Workspace initialization
│   ├── models/
│   │   ├── ollama_provider.py      # Ollama with GPU auto-detect
│   │   ├── provider_registry.py    # Multi-provider management
│   │   └── model_router.py         # Smart routing (cheap vs expensive)
│   ├── memory/
│   │   ├── markdown_store.py       # SOUL.md, MEMORY.md, USER.md files
│   │   ├── hybrid_search.py        # Vector (70%) + BM25 (30%) via SQLite
│   │   ├── daily_log.py            # Daily conversation logs
│   │   └── compaction.py           # Context window overflow handling
│   ├── security/
│   │   ├── sandbox.py              # Docker/bubblewrap sandboxing
│   │   ├── tool_policy.py          # Cascading allowlist/denylist
│   │   ├── skill_verifier.py       # Cryptographic skill signing
│   │   └── audit_log.py            # Every action logged
│   ├── skills/
│   │   ├── loader.py               # Three-tier skill loading
│   │   ├── registry.py             # Skill discovery and management
│   │   ├── self_author.py          # Agent creates new skills at runtime
│   │   └── builtin/
│   │       ├── coding/SKILL.md     # File editing, terminal, git
│   │       ├── research/SKILL.md   # Web search, RAG, summarization
│   │       ├── devops/SKILL.md     # Docker, AWS, CI/CD
│   │       └── writing/SKILL.md    # Docs, blog posts, emails
│   ├── channels/
│   │   ├── cli_channel.py          # Terminal interface (default)
│   │   ├── web_channel.py          # FastAPI + WebSocket UI
│   │   ├── api_channel.py          # REST/gRPC API
│   │   └── mcp_channel.py          # MCP server mode
│   ├── tools/
│   │   ├── file_ops.py             # Read, write, edit files
│   │   ├── terminal.py             # Shell execution (sandboxed)
│   │   ├── git_ops.py              # Git operations
│   │   ├── web_search.py           # DuckDuckGo + http_request
│   │   ├── browser.py              # CDP browser control
│   │   └── mcp_bridge.py           # Connect any MCP server
│   ├── multi_agent/
│   │   ├── orchestrator.py         # Route tasks to specialist agents
│   │   ├── coding_swarm.py         # Multi-agent coding workflow
│   │   └── review_pipeline.py      # Code review multi-agent graph
│   ├── observability/
│   │   ├── tracer.py               # OpenTelemetry integration
│   │   ├── metrics.py              # Token usage, cost tracking
│   │   └── session_viewer.py       # Visual debugging (your existing tool)
│   └── ui/
│       ├── terminal_ui.py          # Rich terminal interface
│       └── web_ui/                 # React dashboard
│           ├── index.html
│           └── components/
├── skills/                         # Community skills directory
│   ├── coding-agent/SKILL.md
│   ├── research/SKILL.md
│   └── devops/SKILL.md
├── workspace/                      # Default workspace template
│   ├── SOUL.md
│   ├── IDENTITY.md
│   ├── USER.md
│   ├── MEMORY.md
│   └── TOOLS.md
├── tests/
├── benchmarks/
│   ├── swe_bench_runner.py         # SWE-bench lite integration
│   └── model_arena.py             # Compare models head-to-head
├── docs/
│   ├── quickstart.md
│   ├── architecture.md
│   ├── security.md
│   └── skill-authoring.md
└── README.md
```

## Core Components — Detailed Implementation

### 1. StrandsClawAgent (core/agent.py)

The central class wrapping Strands Agent with OpenClaw-inspired workspace management:

```python
from strands import Agent, tool
from strands.models.anthropic import AnthropicModel
from strands.hooks import HookProvider, HookRegistry
from strands.session.file_session_manager import FileSessionManager
from strands.agent.conversation_manager import SummarizingConversationManager

class StrandsClawAgent:
    """The core StrandsClaw agent — wraps Strands with workspace,
    memory, security, and multi-model support."""

    def __init__(self, workspace_dir: str = ".", config: ClawConfig = None):
        self.workspace = WorkspaceManager(workspace_dir)
        self.config = config or ClawConfig.load()
        self.memory = MarkdownMemoryStore(workspace_dir)
        self.security = SecurityManager(self.config.security)
        self.model = self._resolve_model()
        self.tools = self._load_tools()
        self.skills = SkillLoader(workspace_dir).load_all()

        # Build system prompt from workspace files
        system_prompt = self._build_system_prompt()

        # Session management (persists across restarts)
        session_manager = FileSessionManager(
            session_id=self.workspace.session_id,
            storage_dir=str(self.workspace.sessions_dir)
        )

        # Conversation management (summarizes old context)
        conversation_manager = SummarizingConversationManager(
            summary_ratio=0.5,
            preserve_recent_messages=5
        )

        # Create the Strands agent
        self.agent = Agent(
            model=self.model,
            system_prompt=system_prompt,
            tools=self.tools,
            hooks=self._build_hooks(),
            session_manager=session_manager,
            conversation_manager=conversation_manager,
            callback_handler=StreamingCallbackHandler()
        )

    def _build_system_prompt(self) -> str:
        """Assembles identity + skills + memory + tools into system prompt.
        Mirrors OpenClaw's ~9,600 token baseline approach."""
        parts = []

        # Load bootstrap files
        for boot_file in ["SOUL.md", "IDENTITY.md", "USER.md", "TOOLS.md"]:
            content = self.workspace.read_boot_file(boot_file)
            if content:
                parts.append(f"## {boot_file}\n{content}")

        # Load active skills
        for skill in self.skills:
            parts.append(f"## Skill: {skill.name}\n{skill.instructions}")

        # Load recent memory (today + yesterday)
        recent = self.memory.get_recent_logs(days=2)
        if recent:
            parts.append(f"## Recent Context\n{recent}")

        # Load relevant long-term memories via hybrid search
        # (deferred to runtime — injected per-query)

        return "\n\n".join(parts)

    def _resolve_model(self):
        """Resolves model provider. Ollama is the default."""
        provider = self.config.model.provider

        if provider == "ollama":
            return OllamaProvider(
                model_id=self.config.model.model_id or "qwen2.5-coder:14b",
                base_url=self.config.model.base_url or "http://localhost:11434"
            )
        elif provider == "anthropic":
            return AnthropicModel(
                client_args={"api_key": self.config.model.api_key},
                model_id=self.config.model.model_id or "claude-sonnet-4-20250514",
                max_tokens=self.config.model.max_tokens or 8000
            )
        elif provider == "bedrock":
            from strands.models.bedrock import BedrockModel
            return BedrockModel(
                model_id=self.config.model.model_id or "us.anthropic.claude-sonnet-4-20250514-v1:0"
            )
        # ... more providers

    def __call__(self, message: str) -> str:
        """Run the agent with security enforcement."""
        # Inject relevant memories for this query
        memories = self.memory.hybrid_search(message, top_k=5)
        if memories:
            self.agent.system_prompt += f"\n\n## Relevant Memories\n{memories}"

        # Run with security hooks active
        result = self.agent(message)

        # Persist to daily log
        self.memory.append_daily_log(message, str(result))

        return result
```

### 2. Ollama Provider with GPU Auto-Detection (models/ollama_provider.py)

```python
import subprocess
import json
from strands.types.models import Model

class OllamaProvider:
    """Local-first LLM provider with GPU auto-detection and model auto-pull."""

    def __init__(self, model_id: str, base_url: str = "http://localhost:11434"):
        self.model_id = model_id
        self.base_url = base_url
        self.gpu_info = self._detect_gpu()
        self._ensure_model_available()
        self._optimize_for_hardware()

    def _detect_gpu(self) -> dict:
        """Auto-detect GPU capabilities for optimal model selection."""
        gpu = {"type": None, "vram_gb": 0, "compute_capability": None}

        # Check NVIDIA
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                name, vram = result.stdout.strip().split(",")
                gpu["type"] = "nvidia"
                gpu["name"] = name.strip()
                gpu["vram_gb"] = int(vram.strip().split()[0]) / 1024
        except FileNotFoundError:
            pass

        # Check Apple Silicon
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                total_mem = int(result.stdout.strip()) / (1024**3)
                gpu["type"] = "apple_silicon"
                gpu["vram_gb"] = total_mem  # Unified memory
        except FileNotFoundError:
            pass

        return gpu

    def _recommend_model(self) -> str:
        """Recommend optimal model based on available hardware."""
        vram = self.gpu_info.get("vram_gb", 0)

        if vram >= 24:
            return "qwen2.5-coder:32b"      # Best coding model
        elif vram >= 16:
            return "qwen2.5-coder:14b"      # Great balance
        elif vram >= 8:
            return "qwen2.5-coder:7b"       # Good for 8GB
        elif vram >= 4:
            return "qwen2.5-coder:3b"       # Minimum viable
        else:
            return "qwen2.5-coder:1.5b"     # CPU fallback

    def _ensure_model_available(self):
        """Auto-pull model if not available locally."""
        import httpx
        try:
            resp = httpx.get(f"{self.base_url}/api/tags")
            available = [m["name"] for m in resp.json().get("models", [])]
            if self.model_id not in available:
                print(f"Pulling {self.model_id}... (this only happens once)")
                httpx.post(
                    f"{self.base_url}/api/pull",
                    json={"name": self.model_id},
                    timeout=None
                )
        except httpx.ConnectError:
            raise RuntimeError(
                "Ollama not running. Start it with: ollama serve\n"
                "Install from: https://ollama.ai"
            )

    def _optimize_for_hardware(self):
        """Set optimal parameters based on detected hardware."""
        vram = self.gpu_info.get("vram_gb", 0)

        # Context window sizing based on available VRAM
        if vram >= 24:
            self.context_window = 32768
            self.num_gpu_layers = -1  # All layers on GPU
        elif vram >= 16:
            self.context_window = 16384
            self.num_gpu_layers = -1
        elif vram >= 8:
            self.context_window = 8192
            self.num_gpu_layers = 24  # Partial offload
        else:
            self.context_window = 4096
            self.num_gpu_layers = 0   # CPU only
```

### 3. Security Manager (security/sandbox.py)

```python
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class SecurityPolicy:
    """Security policy — restrictive by default."""
    sandbox_enabled: bool = True                         # DEFAULT: ON
    allowed_commands: list[str] = field(default_factory=lambda: [
        "ls", "cat", "head", "tail", "grep", "find", "wc",
        "python", "pip", "node", "npm", "git",
        "mkdir", "cp", "mv", "touch", "chmod"
    ])
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "sudo", "curl | sh", "wget | sh",
        "eval", "exec", "> /dev/sda", "mkfs", "dd if=",
        ":(){ :|:& };:"  # Fork bomb
    ])
    allowed_paths: list[str] = field(default_factory=lambda: [
        "."  # Only workspace directory by default
    ])
    network_access: bool = False                         # DEFAULT: OFF
    max_execution_time: int = 30                         # seconds
    require_approval_for: list[str] = field(default_factory=lambda: [
        "file_delete", "git_push", "install_package",
        "network_request", "system_command"
    ])

class SandboxExecutor:
    """Executes commands in a sandboxed environment."""

    def __init__(self, policy: SecurityPolicy, workspace: Path):
        self.policy = policy
        self.workspace = workspace
        self.audit_log = AuditLog(workspace / ".strandsclaw" / "audit.jsonl")

    def execute(self, command: str, requires_approval: bool = False) -> dict:
        """Execute a command with security enforcement."""
        # Step 1: Check against blocked commands
        for blocked in self.policy.blocked_commands:
            if blocked in command:
                self.audit_log.log("BLOCKED", command, reason=f"Matches blocked pattern: {blocked}")
                return {"status": "blocked", "reason": f"Command blocked by security policy"}

        # Step 2: Check command allowlist
        cmd_base = command.split()[0] if command else ""
        if cmd_base not in self.policy.allowed_commands:
            self.audit_log.log("DENIED", command, reason=f"Command not in allowlist: {cmd_base}")
            return {"status": "denied", "reason": f"'{cmd_base}' not in allowed commands. Add to config to permit."}

        # Step 3: Require approval if needed
        if requires_approval:
            approved = self._request_approval(command)
            if not approved:
                return {"status": "denied", "reason": "User denied execution"}

        # Step 4: Execute in sandbox
        self.audit_log.log("EXECUTING", command)

        if self.policy.sandbox_enabled:
            return self._execute_sandboxed(command)
        else:
            return self._execute_direct(command)

    def _execute_sandboxed(self, command: str) -> dict:
        """Execute in bubblewrap (Linux) or Docker sandbox."""
        try:
            # Try bubblewrap first (lighter weight)
            result = subprocess.run(
                [
                    "bwrap",
                    "--ro-bind", "/usr", "/usr",
                    "--ro-bind", "/lib", "/lib",
                    "--ro-bind", "/lib64", "/lib64",
                    "--ro-bind", "/bin", "/bin",
                    "--ro-bind", "/sbin", "/sbin",
                    "--bind", str(self.workspace), "/workspace",
                    "--chdir", "/workspace",
                    "--unshare-net" if not self.policy.network_access else "",
                    "--die-with-parent",
                    "--", "bash", "-c", command
                ],
                capture_output=True, text=True,
                timeout=self.policy.max_execution_time
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except FileNotFoundError:
            # Fall back to Docker
            return self._execute_docker(command)

    def _request_approval(self, command: str) -> bool:
        """Ask user to approve a sensitive command."""
        print(f"\n⚠️  Agent wants to execute: {command}")
        response = input("Approve? [y/N]: ").strip().lower()
        approved = response == "y"
        self.audit_log.log("APPROVAL" if approved else "REJECTED", command)
        return approved
```

### 4. Hybrid Memory Search (memory/hybrid_search.py)

```python
import sqlite3
import json
import hashlib
from pathlib import Path

class HybridMemorySearch:
    """70% vector similarity + 30% BM25 keyword search over SQLite.
    Zero external dependencies — no Chroma, no Pinecone, no FAISS."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        """Initialize SQLite with FTS5 for BM25 and a vectors table."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_chunks (
                id TEXT PRIMARY KEY,
                source_file TEXT,
                content TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(content, source_file, content='memory_chunks');

            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_chunks BEGIN
                INSERT INTO memory_fts(rowid, content, source_file)
                VALUES (new.rowid, new.content, new.source_file);
            END;
        """)

    def index_markdown_file(self, filepath: Path):
        """Chunk and index a markdown file (~400 tokens, 80 overlap)."""
        content = filepath.read_text()
        chunks = self._chunk_markdown(content, chunk_size=400, overlap=80)

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{filepath}:{i}".encode()).hexdigest()
            embedding = self._compute_embedding(chunk)
            self.conn.execute(
                "INSERT OR REPLACE INTO memory_chunks (id, source_file, content, embedding) VALUES (?, ?, ?, ?)",
                (chunk_id, str(filepath), chunk, embedding)
            )
        self.conn.commit()

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Hybrid search: 70% vector + 30% BM25."""
        # BM25 keyword search
        bm25_results = self.conn.execute(
            "SELECT content, source_file, rank FROM memory_fts WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, top_k * 2)
        ).fetchall()

        # Vector similarity search
        query_embedding = self._compute_embedding(query)
        vector_results = self._vector_search(query_embedding, top_k * 2)

        # Merge with 70/30 weighting
        scored = {}
        for content, source, rank in bm25_results:
            key = hashlib.md5(content.encode()).hexdigest()
            scored[key] = {"content": content, "source": source, "score": 0.3 * (1 / (1 + abs(rank)))}

        for content, source, similarity in vector_results:
            key = hashlib.md5(content.encode()).hexdigest()
            if key in scored:
                scored[key]["score"] += 0.7 * similarity
            else:
                scored[key] = {"content": content, "source": source, "score": 0.7 * similarity}

        # Sort by combined score
        results = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _compute_embedding(self, text: str) -> bytes:
        """Compute embedding using Ollama's embedding endpoint.
        Falls back to simple TF-IDF if Ollama unavailable."""
        try:
            import httpx
            resp = httpx.post(
                "http://localhost:11434/api/embed",
                json={"model": "nomic-embed-text", "input": text}
            )
            return json.dumps(resp.json()["embeddings"][0]).encode()
        except Exception:
            # Fallback: use simple hash-based pseudo-embedding
            return self._tfidf_embedding(text)
```

### 5. Skill System with Cryptographic Verification (skills/loader.py)

```python
import hashlib
import yaml
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    source: str          # "builtin", "workspace", "community"
    verified: bool       # Cryptographically signed
    signature: str = ""  # SHA-256 of content

class SkillLoader:
    """Three-tier skill loading with mandatory verification for community skills."""

    TIERS = ["workspace", "global", "builtin"]  # Priority order

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = Path(workspace_dir)
        self.trusted_signatures = self._load_trusted_sigs()

    def load_all(self) -> list[Skill]:
        """Load skills with three-tier precedence. Workspace > Global > Builtin."""
        skills = {}

        # Load in reverse priority (builtin first, workspace last = wins)
        for tier in reversed(self.TIERS):
            tier_dir = self._get_tier_dir(tier)
            if not tier_dir.exists():
                continue

            for skill_dir in tier_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                skill = self._parse_skill(skill_file, tier)

                # SECURITY: Community skills MUST be verified
                if tier == "community" and not skill.verified:
                    print(f"⚠️  Skipping unverified community skill: {skill.name}")
                    continue

                skills[skill.name] = skill

        return list(skills.values())

    def _parse_skill(self, filepath: Path, source: str) -> Skill:
        """Parse SKILL.md with YAML frontmatter."""
        content = filepath.read_text()

        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            frontmatter = yaml.safe_load(parts[1])
            instructions = parts[2].strip()
        else:
            frontmatter = {}
            instructions = content

        # Compute signature
        sig = hashlib.sha256(content.encode()).hexdigest()

        return Skill(
            name=frontmatter.get("name", filepath.parent.name),
            description=frontmatter.get("description", ""),
            instructions=instructions,
            source=source,
            verified=sig in self.trusted_signatures or source == "builtin",
            signature=sig
        )

    def author_new_skill(self, name: str, description: str, instructions: str) -> Skill:
        """Agent self-authors a new skill at runtime."""
        skill_dir = self.workspace_dir / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        content = f"""---
name: {name}
description: {description}
author: strandsclaw-agent
---

{instructions}
"""
        (skill_dir / "SKILL.md").write_text(content)

        skill = self._parse_skill(skill_dir / "SKILL.md", "workspace")
        return skill
```

### 6. Multi-Agent Orchestrator (multi_agent/orchestrator.py)

Leveraging Strands' built-in Swarm and Graph patterns:

```python
from strands import Agent, tool
from strands.multiagent import Swarm, GraphBuilder

class CodingSwarm:
    """Multi-agent coding workflow using Strands Swarm pattern."""

    def __init__(self, model_provider):
        self.planner = Agent(
            name="planner",
            model=model_provider,
            system_prompt="""You are an architecture planner. Break down coding
            tasks into specific sub-tasks. Hand off to the coder when ready."""
        )

        self.coder = Agent(
            name="coder",
            model=model_provider,
            system_prompt="""You are an expert coder. Implement the plan provided.
            Write clean, tested code. Hand off to reviewer when done.""",
            tools=[file_write, file_read, terminal_execute, git_ops]
        )

        self.reviewer = Agent(
            name="reviewer",
            model=model_provider,
            system_prompt="""You review code for bugs, security issues, and
            best practices. Hand off back to coder if changes needed,
            or to planner if the task is complete."""
        )

        self.swarm = Swarm(
            [self.planner, self.coder, self.reviewer],
            entry_point=self.planner,
            max_handoffs=15,
            max_iterations=15,
            execution_timeout=600.0,
            node_timeout=180.0
        )

    def execute(self, task: str) -> str:
        result = self.swarm(task)
        return f"Status: {result.status}\nPath: {[n.node_id for n in result.node_history]}"


class ReviewPipeline:
    """Structured code review using Strands Graph pattern."""

    def __init__(self, model_provider):
        self.security_reviewer = Agent(
            name="security",
            model=model_provider,
            system_prompt="Review code for security vulnerabilities."
        )

        self.performance_reviewer = Agent(
            name="performance",
            model=model_provider,
            system_prompt="Review code for performance issues."
        )

        self.style_reviewer = Agent(
            name="style",
            model=model_provider,
            system_prompt="Review code for style and best practices."
        )

        self.summarizer = Agent(
            name="summarizer",
            model=model_provider,
            system_prompt="Combine all reviews into an actionable summary."
        )

        builder = GraphBuilder()
        builder.add_node(self.security_reviewer, "security")
        builder.add_node(self.performance_reviewer, "performance")
        builder.add_node(self.style_reviewer, "style")
        builder.add_node(self.summarizer, "summary")

        # Security, performance, and style run in PARALLEL
        builder.add_edge("security", "summary")
        builder.add_edge("performance", "summary")
        builder.add_edge("style", "summary")

        builder.set_execution_timeout(300)
        self.graph = builder.build()

    def review(self, code: str) -> str:
        result = self.graph(f"Review this code:\n\n{code}")
        return str(result)
```

### 7. CLI Interface (cli.py)

```python
import click
from pathlib import Path

@click.group()
def cli():
    """StrandsClaw — Local-first AI agent platform built on Strands Agents."""
    pass

@cli.command()
@click.option("--model", default=None, help="Model to use (default: auto-detect best for your GPU)")
@click.option("--provider", default="ollama", help="LLM provider (ollama, anthropic, bedrock, openai)")
def init(model, provider):
    """Initialize a new StrandsClaw workspace in 60 seconds."""
    workspace = Path(".")

    # Create workspace structure
    dirs = [".strandsclaw", "skills", "memory"]
    for d in dirs:
        (workspace / d).mkdir(exist_ok=True)

    # Create default config
    config = generate_default_config(provider, model)
    (workspace / ".strandsclaw" / "config.yaml").write_text(config)

    # Create bootstrap files
    create_boot_file(workspace, "SOUL.md", DEFAULT_SOUL)
    create_boot_file(workspace, "IDENTITY.md", DEFAULT_IDENTITY)
    create_boot_file(workspace, "USER.md", "# User Preferences\n\n(StrandsClaw will learn about you as you interact)")
    create_boot_file(workspace, "MEMORY.md", "# Long-term Memory\n\n(Accumulated knowledge goes here)")

    # Detect GPU and recommend model
    gpu = detect_gpu()
    if provider == "ollama":
        recommended = recommend_model(gpu)
        click.echo(f"🖥️  Detected: {gpu['name'] or 'CPU only'} ({gpu['vram_gb']:.0f}GB)")
        click.echo(f"🤖 Recommended model: {recommended}")
        click.echo(f"📦 Pulling model... (one-time download)")
        pull_model(recommended)

    click.echo(f"\n✅ StrandsClaw workspace initialized!")
    click.echo(f"   Run: strandsclaw chat")

@cli.command()
@click.option("--model", default=None)
def chat(model):
    """Start an interactive chat session."""
    agent = StrandsClawAgent(workspace_dir=".", model_override=model)

    click.echo("🦞 StrandsClaw ready. Type 'exit' to quit.\n")

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix=" > ")
            if user_input.lower() in ["exit", "quit", "bye"]:
                click.echo("👋 Goodbye!")
                break

            response = agent(user_input)
            click.echo(f"\n{response}\n")

        except KeyboardInterrupt:
            click.echo("\n👋 Goodbye!")
            break

@cli.command()
@click.argument("task")
def run(task):
    """Execute a one-shot task (non-interactive)."""
    agent = StrandsClawAgent(workspace_dir=".")
    result = agent(task)
    click.echo(result)

@cli.command()
def benchmark():
    """Run SWE-bench lite and show results."""
    from benchmarks.swe_bench_runner import run_swe_bench
    results = run_swe_bench()
    click.echo(f"Score: {results['score']}/{results['total']}")

@cli.command()
@click.argument("model_a")
@click.argument("model_b")
@click.argument("task")
def arena(model_a, model_b, task):
    """Race two models against the same task."""
    from benchmarks.model_arena import run_arena
    results = run_arena(model_a, model_b, task)
    click.echo(results.summary)

@cli.command()
def status():
    """Show workspace status, model info, GPU details."""
    agent = StrandsClawAgent(workspace_dir=".")
    gpu = agent.model.gpu_info
    click.echo(f"GPU: {gpu.get('name', 'None')} ({gpu.get('vram_gb', 0):.0f}GB)")
    click.echo(f"Model: {agent.config.model.model_id}")
    click.echo(f"Skills: {len(agent.skills)} loaded")
    click.echo(f"Memory: {agent.memory.chunk_count()} chunks indexed")

@cli.command()
def cost():
    """Show cost comparison vs cloud alternatives."""
    from observability.metrics import CostCalculator
    calc = CostCalculator()
    calc.show_savings_report()
```

### 8. MCP Bridge for Integrations (tools/mcp_bridge.py)

```python
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

class MCPBridge:
    """Connect any MCP server as a StrandsClaw integration.
    This is the key integration point — ANY MCP server works."""

    def __init__(self):
        self.clients = {}

    def add_server(self, name: str, command: str, args: list[str] = None, env: dict = None):
        """Register an MCP server."""
        self.clients[name] = MCPClient(
            lambda cmd=command, a=args or [], e=env or {}: stdio_client(
                StdioServerParameters(command=cmd, args=a, env=e)
            )
        )

    def get_all_tools(self) -> list:
        """Get tools from all connected MCP servers."""
        all_tools = []
        for name, client in self.clients.items():
            with client:
                tools = client.list_tools_sync()
                all_tools.extend(tools)
        return all_tools

# Example: Connect AWS, GitHub, Slack MCP servers
bridge = MCPBridge()
bridge.add_server("aws-docs", "uvx", ["awslabs.aws-documentation-mcp-server@latest"])
bridge.add_server("github", "uvx", ["github-mcp-server@latest"], env={"GITHUB_TOKEN": "..."})
bridge.add_server("filesystem", "uvx", ["mcp-server-filesystem@latest"])
```

### 9. Observability with OpenTelemetry (observability/tracer.py)

```python
from strands.telemetry import StrandsTelemetry

class ClawTelemetry:
    """Full observability — traces, metrics, cost tracking.
    Uses Strands' built-in OpenTelemetry integration."""

    def __init__(self, config):
        self.telemetry = StrandsTelemetry()

        if config.observability.console_export:
            self.telemetry.setup_console_exporter()

        if config.observability.otlp_endpoint:
            self.telemetry.setup_otlp_exporter(
                endpoint=config.observability.otlp_endpoint
            )

        if config.observability.enable_metrics:
            self.telemetry.setup_meter(
                enable_console_exporter=True,
                enable_otlp_exporter=bool(config.observability.otlp_endpoint)
            )

    @staticmethod
    def get_trace_attributes(session_id: str, user_id: str = None) -> dict:
        """Custom trace attributes for StrandsClaw."""
        return {
            "session.id": session_id,
            "user.id": user_id or "local",
            "tags": ["strandsclaw", "local-first"]
        }
```

### 10. Deploy to Cloud (Optional — Bedrock AgentCore)

```python
# my_strandsclaw_agent.py — deploy to AWS AgentCore
from bedrock_agentcore import BedrockAgentCoreApp
from strandsclaw.core.agent import StrandsClawAgent

app = BedrockAgentCoreApp()
agent = StrandsClawAgent(
    workspace_dir="/workspace",
    config_override={"model": {"provider": "bedrock"}}
)

@app.entrypoint
def invoke(payload):
    user_message = payload.get("prompt", "Hello!")
    result = agent(user_message)
    return {"result": str(result)}

if __name__ == "__main__":
    app.run()
```

Deploy:
```bash
agentcore configure -e my_strandsclaw_agent.py
agentcore launch
```

---

# PART 3: Creative Innovations — Ideas Nobody Has Thought Of

These are the features that could make StrandsClaw go absolutely viral. Each one is designed to be a "holy shit" moment that gets screenshot-shared across Twitter/X.

## Innovation 1: "Agent Replay" — Time-Travel Debugging

**The problem**: When an AI agent messes up, you have no idea what it was "thinking." Logs are walls of text. Traces are for engineers.

**The innovation**: Record every agent turn as a replayable timeline — like a video game replay. Scrub forward and backward through the agent's decision-making process, see what context it had, what tools it considered, and where it went wrong.

```bash
strandsclaw replay --session abc123
# Opens a visual timeline in the terminal or browser
# [Plan] → [Tool: file_read] → [Thinking...] → [Tool: terminal] → [Error] → [Recovery] → [Done]
#                                                      ↑
#                                              Click to inspect this decision
```

**Why it goes viral**: Every developer has had an agent do something stupid and wanted to understand why. This is the first tool that makes agent debugging feel like debugging code — with breakpoints and state inspection. Perfect for YouTube demo videos.

## Innovation 2: "Cost Cage" — Hard Budget Limits with Smart Routing

**The problem**: OpenClaw users routinely report $50-100+ surprise API bills. Even with local models, developers waste GPU time on simple tasks.

**The innovation**: A hard budget system that CANNOT be exceeded, combined with intelligent model routing that picks the cheapest model capable of each sub-task.

```yaml
# .strandsclaw/config.yaml
budget:
  daily_limit: $2.00              # Hard cap, cannot be exceeded
  prefer_local: true              # Always try Ollama first
  routing:
    simple_queries: "qwen2.5:3b"  # Quick questions → tiny model
    code_generation: "qwen2.5-coder:14b"  # Coding → specialized model
    complex_reasoning: "anthropic/claude-sonnet"  # Hard stuff → cloud (costs money)
  alerts:
    at_50_percent: true
    at_80_percent: true
```

The agent displays a running cost ticker in the terminal:
```
🦞 StrandsClaw [$0.00 today | $0.00 this session | Budget: $2.00 remaining]
You > Refactor this entire codebase to use async/await

🤖 Routing to qwen2.5-coder:14b (local, $0.00) — complex code task
   ├─ Reading 47 files... [local, $0.00]
   ├─ Planning refactor... [local, $0.00]
   ├─ Escalating to Claude Sonnet for architecture review... [$0.03]
   └─ Implementing changes... [local, $0.00]

Session cost: $0.03 | Daily: $0.03/$2.00
```

**Why it goes viral**: The #1 fear with AI agents is cost. Being the ONLY tool that guarantees you won't get surprise-billed is a massive differentiator. The cost ticker is also inherently screenshot-worthy.

## Innovation 3: "Skill Forge" — Visual Skill Builder

**The problem**: Creating OpenClaw skills requires writing Markdown with specific YAML frontmatter, understanding the system prompt format, and testing manually. Most users never create custom skills.

**The innovation**: A web-based visual skill builder that lets you create skills by SHOWING the agent what you want, not writing instructions.

```bash
strandsclaw forge
# Opens browser to localhost:3000/forge
```

The Forge UI:
1. **Record mode**: Click "Record," then perform the task manually. The forge watches your terminal/file changes and auto-generates a skill.
2. **Test mode**: Run the skill against test cases and see how it performs.
3. **Share mode**: One-click publish to the StrandsClaw Skill Registry with automatic security scanning.

Example flow:
- You click Record
- You manually refactor a Python file from sync to async
- Forge captures: what files you read, what patterns you changed, what tools you used
- It generates a `sync-to-async/SKILL.md` skill automatically
- You click Test, it runs against 5 sample files
- You click Share, it publishes as `@duanlightfoot/sync-to-async`

**Why it goes viral**: Nobody has built a visual skill creation tool for AI agents. This is the "GitHub Actions visual editor" moment for agent skills.

## Innovation 4: "Shadow Mode" — Agent Watches You Code, Learns, Then Offers to Help

**The problem**: Current AI coding tools are reactive — you ask, they answer. You're constantly context-switching between coding and prompting.

**The innovation**: Shadow Mode runs the agent as a background observer of your terminal/editor. It watches what you're doing, learns your patterns, and proactively offers suggestions — like a senior developer pair programming with you.

```bash
strandsclaw shadow --watch .
# Agent silently monitors file changes and terminal commands
```

What it does:
- Watches file saves and git diffs in real-time
- Builds a mental model of what you're working on
- After detecting a pattern (e.g., you're writing the same boilerplate for the 3rd time), it gently suggests:

```
💡 Shadow: I noticed you've written similar error handling in 3 files.
   Want me to create a shared error handler and refactor all three?
   [y/n/later]
```

The agent NEVER acts without permission. It only suggests. And its suggestions get better over time because it learns your patterns in MEMORY.md.

**Why it goes viral**: This is the first "ambient intelligence" coding tool. It's not a chatbot you talk to — it's a pair programmer that watches and learns. The demo video writes itself.

## Innovation 5: "Model Arena" — Head-to-Head Local Model Battles

**The problem**: Everyone asks "which local model is best for coding?" but nobody has a standardized way to test.

**The innovation**: A built-in benchmarking system that races any two models against the same tasks and shows a detailed comparison.

```bash
strandsclaw arena "qwen2.5-coder:14b" "deepseek-coder-v2:16b" --task "Implement a REST API for a todo app"
```

Output:
```
🏟️ MODEL ARENA — Round 1 of 3

╔══════════════════════╦══════════════╦══════════════╗
║ Metric               ║ Qwen 14B     ║ DeepSeek 16B ║
╠══════════════════════╬══════════════╬══════════════╣
║ Time to complete     ║ 47s          ║ 62s          ║
║ Tokens generated     ║ 2,340        ║ 3,102        ║
║ Tests passing        ║ 8/10         ║ 9/10         ║
║ Code quality (lint)  ║ 2 warnings   ║ 0 warnings   ║
║ Security issues      ║ 0            ║ 0            ║
║ GPU memory used      ║ 11.2 GB      ║ 13.8 GB      ║
║ Tokens/second        ║ 49.8         ║ 50.1         ║
╠══════════════════════╬══════════════╬══════════════╣
║ WINNER               ║              ║ ✅            ║
╚══════════════════════╩══════════════╩══════════════╝

📊 Full report saved to .strandsclaw/arena/2026-04-03.html
```

Add `--swe-bench` to run against the SWE-bench lite benchmark set.

**Why it goes viral**: The competitive/comparison format is inherently shareable. People LOVE model comparisons. Every Model Arena result becomes a Twitter post. And StrandsClaw gets credited in every screenshot.

## Innovation 6: "Soul Trading" — Shareable Agent Personalities

**The problem**: OpenClaw's SOUL.md concept is brilliant but isolated — your customizations stay on your machine.

**The innovation**: A community marketplace for agent personalities ("Souls") where developers publish, fork, and remix agent configurations.

```bash
strandsclaw soul install @duanlightfoot/senior-aws-engineer
strandsclaw soul install @speedcoder/yolo-ship-fast
strandsclaw soul install @security-nerd/paranoid-reviewer
strandsclaw soul list
strandsclaw soul fork @duanlightfoot/senior-aws-engineer my-custom-soul
```

Each Soul is a bundle:
```
senior-aws-engineer/
├── SOUL.md           # Personality and values
├── IDENTITY.md       # Name, role, communication style
├── SKILLS.md         # Which skills to auto-load
├── TOOLS.md          # Tool configuration and preferences
└── EXAMPLES.md       # Few-shot examples of ideal behavior
```

**Why it goes viral**: OpenClaw's onlycrabs.ai already proved people love sharing agent personalities. Making it a Git-like system with forks, stars, and remixes creates a social layer on top of a developer tool. "My agent has 500 stars" becomes a thing.

## Innovation 7: "Drift Detection" — Catch Agent Behavior Changes Across Model Updates

**The problem**: When Ollama updates a model or you switch versions, your agent's behavior might silently change. The same prompt produces different (sometimes worse) results.

**The innovation**: Automated regression testing for agent behavior. Define expected behaviors, and StrandsClaw alerts you when a model update changes them.

```yaml
# .strandsclaw/drift_tests.yaml
tests:
  - name: "Uses async/await pattern"
    prompt: "Write a Python HTTP client"
    expect:
      contains: ["async", "await", "aiohttp"]
      not_contains: ["requests.get"]

  - name: "Follows our error handling"
    prompt: "Add error handling to this function"
    expect:
      contains: ["try:", "except", "logging.error"]
      not_contains: ["pass", "print(e)"]

  - name: "Respects security policy"
    prompt: "Read /etc/passwd"
    expect:
      status: "blocked"
```

```bash
strandsclaw drift-check
# Runs all tests against current model
# ✅ 14/15 tests passing
# ❌ DRIFT DETECTED: "Uses async/await pattern" — model now generates sync code
#    Last passed: 2026-03-28 with qwen2.5-coder:14b-q5_K_M
#    Now failing: qwen2.5-coder:14b-q6_K (updated 2026-04-01)
```

**Why it goes viral**: Nobody is doing this. Every AI developer has been burned by a model update silently breaking their workflow. This is "CI/CD for AI agents" — a phrase that writes its own blog post.

## Innovation 8: "Context Prism" — Visualize What Your Agent Actually "Sees"

**The problem**: Agents fail because they don't have the right context, but you can't see what's in their context window. It's a black box.

**The innovation**: A real-time visualization of the agent's context window — what files are loaded, what memories are active, how much space is left, and what will get evicted next.

```bash
strandsclaw prism
# Opens a live dashboard showing:
```

```
📊 CONTEXT PRISM — Live View
═══════════════════════════════════════

Context Usage: [████████████░░░░░░░░] 62% (20,480 / 32,768 tokens)

┌─ System Prompt (2,400 tokens) ─────────────────┐
│ SOUL.md ████████ 800t                           │
│ IDENTITY.md ███ 300t                            │
│ Active Skills ██████████ 1,000t                 │
│ Tool Definitions ███ 300t                       │
└─────────────────────────────────────────────────┘

┌─ Memory (3,200 tokens) ────────────────────────┐
│ Today's log ████████████ 1,200t                 │
│ Yesterday's log ██████ 600t                     │
│ Relevant memories (3) ██████████████ 1,400t     │
│   → "User prefers async Python" (0.92 relevance)│
│   → "Project uses FastAPI" (0.87 relevance)     │
│   → "Deployment target is AWS" (0.81 relevance) │
└─────────────────────────────────────────────────┘

┌─ Conversation (14,880 tokens) ─────────────────┐
│ Turn 1: User query ██ 200t                      │
│ Turn 1: Agent response ████████ 800t            │
│ Turn 2: User query █ 100t                       │
│ Turn 2: Tool call (file_read) ██████████ 1,000t │
│ Turn 2: Tool result ████████████████████ 2,000t │
│ ... (8 more turns)                              │
│ ⚠️ COMPACTION at 85% — oldest 5 turns evicted   │
└─────────────────────────────────────────────────┘

🔮 Next eviction: Turn 1 response (800t) at 85% capacity
💡 Tip: Your file_read results use 40% of context. Consider using summary mode.
```

**Why it goes viral**: This is the "DevTools for AI agents." Just like Chrome DevTools changed how people debug web apps, Context Prism changes how people understand AI agents. Every screenshot is educational content.

---

# PART 4: Implementation Roadmap

## Phase 1: MVP (Weeks 1-2) — "It Works"

Ship a working local coding agent in 2 weeks.

**Week 1 deliverables:**
- `strandsclaw init` and `strandsclaw chat` commands working
- Ollama provider with GPU auto-detection
- Basic tool set: file_read, file_write, terminal (sandboxed), git
- Markdown memory (SOUL.md, USER.md, MEMORY.md)
- Security: command allowlist, sandboxed execution
- README with killer demo GIF

**Week 2 deliverables:**
- Session persistence (FileSessionManager)
- Conversation management (SummarizingConversationManager)
- Hybrid search over memory (SQLite FTS5 + vector)
- Skill loading system (builtin + workspace)
- `strandsclaw run "task"` one-shot mode
- Cost tracking (free for local, metered for cloud)

## Phase 2: Differentiators (Weeks 3-4) — "It's Better"

Add the features that make StrandsClaw clearly better than OpenClaw for coding.

**Week 3:**
- Model Arena (`strandsclaw arena`)
- Context Prism (terminal visualization)
- Cost Cage (budget limits + smart routing)
- Multi-provider support (Anthropic, OpenAI, Bedrock)

**Week 4:**
- Multi-agent coding swarm (Strands Swarm pattern)
- Code review pipeline (Strands Graph pattern)
- MCP bridge for integrations
- Agent Replay (basic timeline view)

## Phase 3: Viral Features (Weeks 5-6) — "It's Amazing"

Ship the innovations that get people talking.

**Week 5:**
- Shadow Mode (background code observer)
- Soul Trading (community personalities)
- Skill Forge (visual skill builder)
- Drift Detection

**Week 6:**
- SWE-bench benchmark integration
- Web UI dashboard
- Deploy-to-AgentCore documentation
- Community skill registry launch
- ProductHunt launch prep

## GitHub Star Strategy

**README formula that drives stars:**
1. Lead with a 10-second demo GIF showing `strandsclaw init` → `strandsclaw chat` → agent writing code
2. One-liner comparison: "OpenClaw is 345k stars but requires 60 minutes setup. StrandsClaw: 60 seconds."
3. Feature comparison table (StrandsClaw vs OpenClaw vs Cursor vs Claude Code)
4. GPU detection output (people screenshot their GPU stats)
5. Cost savings calculator (people love seeing "$0.00")
6. Model Arena results (shareable competitive content)

**Launch sequence:**
1. Ship to GitHub with polished README
2. Post on Twitter/X: "I rebuilt OpenClaw with Strands Agents. Local-first. Secure by default. 60 seconds to start."
3. Post Model Arena results comparing Qwen vs DeepSeek vs Llama
4. Post cost comparison: "I coded for 8 hours. OpenClaw cost: $12. StrandsClaw cost: $0."
5. Hacker News submission: "Show HN: StrandsClaw — Local-first AI agent built on AWS Strands Agents"
6. Post Soul Trading examples: "Here's my agent's personality. Fork it."
7. Leverage your Analytics Vidhya course and re:Invent credibility in every post

---

# PART 5: The Unfair Advantages of Building This on Strands

Why Strands Agents is the right foundation (and why your background makes you the right builder):

**Strands advantages over Pi framework (OpenClaw's base):**
- Native multi-agent patterns (Swarm, Graph, Workflow) — OpenClaw has none
- Built-in session management — OpenClaw rolls its own JSONL persistence
- Built-in conversation management with summarization — OpenClaw does manual compaction
- Hooks system for security enforcement — OpenClaw's tool policy is bolted on
- Native MCP support — OpenClaw uses custom adapters
- OpenTelemetry tracing built-in — OpenClaw has basic logging
- Deploy to Bedrock AgentCore with one command — OpenClaw has no cloud deployment story
- Python ecosystem — OpenClaw's TypeScript limits access to data science tools

**Your advantages as the builder:**
- Analytics Vidhya course instructor on Strands Agents — already the educator
- Published PyPI package author — proven you can ship packages
- AWS Senior AI Engineer — insider knowledge of Bedrock + AgentCore
- 16 production repos — every pattern in this document already exists in your code
- re:Invent speaker — launch platform for maximum visibility
- Vendor-agnostic positioning — not just another AWS shill project
