# Confluence Retriever: AI-Powered Wiki Search

**Tech Group Presentation**

---

## Introduction

### The Problem

Your AI assistant is incredibly powerful — it can write code, debug issues, explain complex systems. But ask it:

> "What's our deployment process for microservices?"

And it draws a blank. Internal documentation lives in Confluence, behind authentication, inaccessible to AI tools.

### The Solution

**confluence-retriever** is a lightweight CLI that bridges this gap:

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   You (User)    │      │   AI Assistant   │      │   Confluence    │
│                 │      │  (Claude, Copilot│      │   REST API      │
│  "How do I      │─────▶│   Codex, Gemini) │      │                 │
│   deploy to     │      │                  │      │                 │
│   prod?"        │      │   ┌──────────┐   │      │                 │
│                 │      │   │search-wiki│──────────▶ CQL Search     │
│                 │◀─────│   │  skill   │◀──────────  Results       │
│  "Here are the  │      │   └──────────┘   │      │                 │
│   steps..."     │      │                  │      │                 │
└─────────────────┘      └──────────────────┘      └─────────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  wiki_answer.py  │
                         │  (Retriever CLI) │
                         │                  │
                         │  • CQL queries   │
                         │  • Result ranking│
                         │  • Markdown out  │
                         └──────────────────┘
```

### Architecture: "Dumb Retriever, Smart Host"

The design philosophy is intentionally simple:

| Component | Responsibility |
|-----------|----------------|
| **CLI** (`wiki_answer.py`) | Search, rank, return markdown — deterministic, testable |
| **AI Assistant** | Synthesize the answer — contextual, intelligent |

**Why this split?**
- ✅ Single credential location (no PAT in every AI tool)
- ✅ Works with any AI assistant (Claude Code, Copilot, Codex, Gemini, etc.)
- ✅ Deterministic ranking covered by 50+ unit tests
- ✅ Token cost controlled by explicit depth flags

---

## What's the Skill For?

### Target Audience

Developers and engineers who:
- Use AI coding assistants (Claude Code, GitHub Copilot, Codex, Gemini)
- Need to reference internal Confluence documentation
- Want controlled, cost-efficient wiki retrieval

### Use Cases

| Scenario | Example Question |
|----------|------------------|
| **Quick link lookup** | "Find the page for our API authentication docs" |
| **Process steps** | "How do I configure the customer API?" |
| **Troubleshooting** | "What's the fix for the LDAP timeout error?" |
| **Verification** | "What's the source of truth for release approvals?" |
| **Deep research** | "Research everything about our deployment pipeline" |

### Key Benefits

1. **Controlled Token Cost** — You choose how deep to search
2. **Consistent Results** — Deterministic ranking algorithm
3. **Assistant Agnostic** — Same CLI works with any AI tool
4. **Secure Credentials** — PAT stays in local `.env` file

---

## How to Use It: Depth Modes

The CLI offers four retrieval depths, each with different cost/detail tradeoffs:

### Depth Comparison

| Depth | API Calls | Pages Fetched | Char Budget | Best For |
|-------|-----------|---------------|-------------|----------|
| `links` | 1 search | 0 | 0 | Quick page discovery |
| `skim` | 1 search + 1 body | 1 | ~1,200 | How-to questions |
| `deep` | 1 search + 3 bodies | 3 | ~6,000 | Verification, comparison |
| `ultra` | 2 searches + 5-7 bodies | 5-7 | ~15,000+ | Exhaustive research |

### Trigger Phrases → Depth Mapping

The AI assistant automatically selects depth based on your wording:

| Your Phrasing | Depth Selected | Why |
|---------------|----------------|-----|
| "find", "where is", "link to", "docs for" | `links` | You want a URL, not content |
| "how do I", "show steps", "troubleshoot", "configure" | `skim` | You need details from one page |
| "verify", "compare", "source of truth", "think harder" | `deep` | You need multiple perspectives |
| "research mode", "exhaustive", "leave no stone unturned" | `ultra` | You want everything |

### CLI Examples

```bash
# Quick link lookup (cheapest)
python3 scripts/wiki_answer.py --query "deployment checklist" --depth links

# Get steps from top page
python3 scripts/wiki_answer.py --query "API authentication" --depth skim

# Verify across multiple pages
python3 scripts/wiki_answer.py --query "release approvals" --depth deep

# Exhaustive research
python3 scripts/wiki_answer.py --query "microservice architecture" --depth ultra
```

### Ultra Mode: What's Different?

Ultra mode adds several enhancements:

1. **Expanded Queries** — Automatically adds structural variants and abbreviation expansions
2. **Parallel Title+Text Search** — Finds pages even when query terms only appear in title
3. **Cross-Link Following** — Fetches up to 2 pages linked from top results
4. **Higher Character Budget** — 3,000 chars per page (vs 1,200 for skim)

```bash
# Example with tuning options
python3 scripts/wiki_answer.py \
  --query "deployment process" \
  --depth ultra \
  --workers 2 \              # Reduce parallelism for rate-limited instances
  --recency-halflife-days 90 # Prefer recently updated pages
```

---

## Live Demo

### Demo 1: Quick Link Lookup

**Prompt to AI Assistant:**
```
Find the wiki page for the deployment checklist.
```

**What the assistant does:**
```bash
python3 scripts/wiki_answer.py \
  --query "deployment checklist" \
  --depth links \
  --limit 5
```

**Sample output:**
```markdown
# Wiki results for 'deployment checklist'

## 1. Production Deployment Checklist
- **Space:** DevOps (`DO`)
- **URL:** https://confluence.example.com/display/DO/Production+Deployment+Checklist
- **Excerpt:** Complete this checklist before deploying to production...

## 2. Release Management Process
- **Space:** Engineering (`ENG`)
- **URL:** https://confluence.example.com/display/ENG/Release+Management+Process
- **Excerpt:** Our release process includes deployment verification...
```

**AI synthesizes:**
> "The deployment checklist is here: https://confluence.example.com/display/DO/Production+Deployment+Checklist"

---

### Demo 2: How-To Question

**Prompt to AI Assistant:**
```
How do I configure customer API authentication according to the wiki?
```

**What the assistant does:**
```bash
python3 scripts/wiki_answer.py \
  --query "customer API authentication" \
  --query "configure authentication" \
  --depth skim \
  --limit 5
```

**Sample output (with body content):**
```markdown
# Wiki results for 'customer API authentication', 'configure authentication'

## 1. Customer API Authentication Guide
- **Space:** API Team (`API`)
- **URL:** https://confluence.example.com/display/API/Customer+API+Authentication+Guide
- **Excerpt:** This guide covers OAuth2 setup for customer-facing APIs...
- **Headings:** Overview, Prerequisites, Configuration Steps, Troubleshooting
- **Relevant passages:**
  - Configuration Steps: To configure authentication, first obtain your client 
    credentials from the developer portal. Set CLIENT_ID and CLIENT_SECRET in 
    your environment. Initialize the OAuth client with: oauth = OAuth2Client(...)
```

**AI synthesizes:**
> "According to the wiki, to configure customer API authentication:
> 1. Obtain client credentials from the developer portal
> 2. Set `CLIENT_ID` and `CLIENT_SECRET` environment variables
> 3. Initialize with `OAuth2Client(...)`
> 
> Full details: https://confluence.example.com/display/API/Customer+API+Authentication+Guide"

---

### Demo 3: Deep Verification

**Prompt to AI Assistant:**
```
Deep search the wiki and verify the source of truth for release approvals.
```

**What the assistant does:**
```bash
python3 scripts/wiki_answer.py \
  --query "release approvals" \
  --query "source of truth" \
  --depth deep \
  --limit 5
```

**What you get:**
- Content from the **top 3 pages**
- Up to **2,000 characters per page** of query-relevant passages
- AI can cross-reference and verify across multiple sources

---

### Demo 4: Ultra Research Mode

**Prompt to AI Assistant:**
```
Ultrathink the wiki about our microservice deployment pipeline.
```

**What the assistant does:**
```bash
python3 scripts/wiki_answer.py \
  --query "microservice deployment pipeline" \
  --depth ultra \
  --limit 5
```

**What happens internally:**
1. Expands query to include variants: "microservice deployment", "deployment pipeline", "deployment"
2. Runs parallel text + title searches
3. Fetches bodies from top 5 pages
4. Follows up to 2 cross-links from those pages
5. Returns ~15,000+ characters of relevant content

---

## How to Install

### Prerequisites

- Python 3.9+
- Network access to your Confluence instance
- A Confluence Personal Access Token (PAT)

### Step 1: Generate a PAT

1. Go to your Confluence instance:
   ```
   https://your-instance.atlassian.net/plugins/servlet/de.resolution.apitokenauth/admin
   ```
   Or: Profile → Personal Access Tokens

2. Create a new token with read access

3. Copy the token (you won't see it again!)

### Step 2: Configure Credentials

```bash
# Create config directory
mkdir -p ~/.config/confluence-retriever

# Create .env file (from template or scratch)
cat > ~/.config/confluence-retriever/.env << 'EOF'
CONFLUENCE_URL=https://your-instance.atlassian.net
CONFLUENCE_PAT=your_token_here
EOF

# Secure permissions
chmod 600 ~/.config/confluence-retriever/.env
```

### Step 3: Install Dependencies

```bash
cd /path/to/confluence-retriever
pip install -r requirements.txt
```

### Step 4: Verify It Works

```bash
python3 scripts/wiki_answer.py --query "test" --limit 1
```

Exit code 0 with results = success! 🎉

### Step 5: Install the AI Skill

The skill tells your AI assistant how to invoke the CLI:

```bash
# For Claude Code
python3 install.py --target claude

# For GitHub Copilot CLI
python3 install.py --target copilot

# For Codex
python3 install.py --target codex

# For Gemini
python3 install.py --target gemini

# For a custom/shared location
python3 install.py --dest /path/to/skills/search-wiki/SKILL.md

# Dry run (see what would be written)
python3 install.py --check
```

**For Copilot CLI:** After installing, run `/skills reload` or restart the session.

### Exit Codes Reference

| Code | Meaning | Fix |
|------|---------|-----|
| 0 | Success | ✅ |
| 2 | Config error | Check `.env` file exists and has both variables |
| 3 | Auth failed | Regenerate PAT (token expired or invalid) |
| 4 | Network error | Check VPN/connectivity |

---

## Results Quality: What Affects It?

### Factor 1: The LLM Model

The **CLI returns the same ranked markdown** regardless of which AI assistant calls it. But the **synthesized answer quality** depends on the model:

| Model Characteristic | Impact on Results |
|---------------------|-------------------|
| Context window size | More results can be processed |
| Reasoning capability | Better synthesis from multiple pages |
| Instruction following | Correct depth selection from user phrasing |
| Factual grounding | Stays closer to wiki content |

**Practical implication:** The same query may produce different quality answers in Claude Opus vs Claude Haiku vs GPT-4 vs Gemini.

### Factor 2: Wiki Content Quality

**Garbage in, garbage out.** The retriever can only find what exists:

| Wiki Quality Issue | Retriever Impact |
|--------------------|------------------|
| Outdated pages | May return stale information |
| Poor titles | Title matches rank lower |
| Missing keywords | Pages not found by CQL |
| Scattered documentation | Multiple low-scoring results |

**Tips for better wiki content:**
- Use descriptive page titles with key terms
- Keep pages updated (ultra mode can use recency decay)
- Link related pages (ultra mode follows cross-links)

### Factor 3: Query Term Selection

The AI assistant extracts query terms from your question. Better terms = better results:

| User Question | Extracted Queries | Quality |
|--------------|-------------------|---------|
| "How does the thing work?" | `thing` | ❌ Too vague |
| "How does authentication work?" | `authentication` | ✅ Specific |
| "How does OAuth2 API auth work?" | `OAuth2`, `API authentication` | ✅✅ Very specific |

### The Ranking Algorithm

Results are scored using keyword matching:

```
Score = Σ(phrase matches) + Σ(token matches)
        └── title matches score higher than excerpt matches
```

- **Phrase match in title:** +10 points
- **Phrase match in excerpt:** +5 points  
- **Token match in title:** +3 points
- **Token match in excerpt:** +1 point

Results are sorted by descending score. The algorithm is deterministic and covered by unit tests.

---

## Conclusion

### Key Takeaways

1. **Bridge the gap** — Give your AI assistant access to internal Confluence documentation
2. **Control your costs** — Four depth levels let you choose token spend
3. **Stay secure** — Credentials stay local, never sent to AI providers
4. **Universal compatibility** — Works with Claude, Copilot, Codex, Gemini, and more

### Depth Quick Reference

| Need | Depth | Prompt Hint |
|------|-------|-------------|
| Just a link | `links` | "find", "where is" |
| Steps/details | `skim` | "how do I", "troubleshoot" |
| Verification | `deep` | "verify", "source of truth" |
| Full research | `ultra` | "exhaustive", "research mode" |

### Getting Started

```bash
# 1. Clone the repo
git clone https://github.com/flyawayfarfar/confluence-retriever.git

# 2. Configure credentials
mkdir -p ~/.config/confluence-retriever
# Edit ~/.config/confluence-retriever/.env

# 3. Install
pip install -r requirements.txt
python3 install.py --target <your-assistant>

# 4. Ask your AI about internal docs!
```

---

## Q&A

**Common Questions:**

**Q: Does this send my wiki content to the AI provider?**
A: The AI assistant receives the markdown output, so yes — but only the capped, relevant passages, not entire pages.

**Q: Can I use this without an AI assistant?**
A: Yes! Run `wiki_answer.py` directly from the command line.

**Q: How do I update the skill after upgrading?**
A: Re-run `python3 install.py --target <assistant>`. For Copilot CLI, run `/skills reload`.

**Q: What if my Confluence instance is on-premise?**
A: Set `CONFLUENCE_URL` to your on-premise URL. Works with both Cloud and Data Center.

---

## Resources

- **Repository:** https://github.com/flyawayfarfar/confluence-retriever
- **PAT Setup Guide:** `confluence-pat-setup.md`
- **Implementation Details:** `confluence-retriever-implementation.md`
- **Copilot CLI Setup:** `COPILOT_CLI_SETUP.md`
