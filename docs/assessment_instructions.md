# Technical Assessment — Extended Term Consultant (ETC) Data Scientist, Department for Outcomes (WKCOD)

## Overview

This assessment evaluates your ability to work with large language models, design modern analytical web applications, reason about measurement and bias challenges, build robust data pipelines, and communicate strategic insights to senior leadership. It is designed to reflect the actual work you would do in this role as an Extended Term Consultant (ETC) Data Scientist.

The assessment consists of three distinct questions:

- **Question 1**: Next-Generation Interactive & LLM-Powered WBG Scorecard Web Prototype
- **Question 2**: CPF-PAD Alignment Case Study: Uncertainty & Bias Analysis
- **Question 3**: Scorecard Analytics & Executive Slide Deck

---

### Time Limit & Candidate Strategy

**Time limit**: **8 hours**

> **Pacing & Calibration Note**: The assessment is calibrated to take approximately **5 to 6 hours of focused work** to complete two questions. The full 8-hour window is provided to give you sufficient time for environment setup, data ingestion testing, visual and editorial polish, replication packaging, and demo recording without unnecessary time pressure. You may use the full window to attempt all three questions, if you wish.

#### Self-Selection & Prioritization:

- **Mandatory Minimum**: Candidates are required to complete **at least two (2) questions** of their choice.
- **Self-Selection as a Self-Declaration**: Deciding which questions to prioritize is an intentional part of the assessment. It serves as a self-declaration of where you see your core strengths and abilities:
  - If your passion lies in rapid engineering, LLM integration, and interactive user experiences, prioritize **Question 1**.
  - If your strength lies in methodological depth, econometrics, measurement error, and analytical experimentation, prioritize **Question 2**.
  - If your expertise is in data pipelines, scorecard analytics, and executive-level visualization/communication for leadership, prioritize **Question 3**.
- **Grading Parity (Quality over Quantity)**:
  - Each completed question is evaluated out of **50 points**, for a total maximum score of **100 points**.
  - Completing 2 questions versus completing all 3 **does not impact or penalize your overall grade**.
  - If you submit 2 questions, your score is the sum of those two questions (100% max).
  - If you choose to attempt all 3 questions, your overall grade will be determined by your **top two scoring questions**, ensuring that candidates who invest their 8 hours deepening two solutions are judged on completely equal footing with those who distribute their time across all three.
- In your top-level `README.md`, simply specify which questions you have chosen to prioritize.

**Submission**: A single `.zip` file containing your full replication package. See [Submission Requirements](#submission-requirements) below.
Email it to Juan Francisco Margitic (jmargitic@worldbank.org), responding to the initial email containing the instructions.

---

## Question 1 — Next-Generation Interactive & LLM-Powered WBG Scorecard Prototype (50 Points)

### Context & Management Mandate

The **WBG Corporate Scorecard** (available at [scorecard.worldbank.org](https://scorecard.worldbank.org)) is the apex results-reporting platform for the World Bank Group. It tracks institutional progress across development outcomes, operational effectiveness, and organizational performance.

Your manager approaches you with a mandate:

> *"We want to take accessibility and analytics for global citizens to the next level. Rather than presenting static dashboards or raw data tables, we want to re-imagine the Scorecard as an immersive, highly interactive web application. Global users—from policymakers and researchers to journalists and ordinary citizens—should be able to explore the data dynamically and ask complex analytical questions in natural language. We want an LLM integrated directly into the app that can intelligently query our indicators database, synthesize findings, and generate accurate insights on demand. Innovation and visual polish are paramount."*

You are asked to build a **working prototype / artifact** of this web application in a few hours.

---

### Step 1 — Review & Familiarization with the WBG Scorecard

Before designing your application, review the live platform at **[https://scorecard.worldbank.org](https://scorecard.worldbank.org)** to understand its structure and narrative:

1. **Outcomes Tab**: Familiarize yourself with the **"Outcome Areas"** (how development goals and thematic priority areas are organized).
2. **Data Tab**: Explore the three primary data sections:
   - **"Vision"**
   - **"Client Context"**
   - **"WBG Results"**

**Note**: You may also draw on other publicly available World Bank data sources for individual projects (such as the [Documents & Reports API](https://documents.worldbank.org)).

---

### Step 2 — Focus Area: WBG Results Data & API Ingestion

For your prototype, your analytical engine should focus specifically on the **WBG Results** indicator database. You may use **Vision** and **Client Context** data to contextualize and compare progress achieved or expected by WBG-financed operations, as reflected in the **WBG Results** indicators.

- **Data Ingestion via API**: Inspect and utilize the API endpoints or network data calls powering the WBG Scorecard website (or its public data download endpoints) to pull and ingest the WBG Results data directly into your application.
- Ensure your ingestion logic cleans, structures, and caches or stores the data efficiently so your application is responsive.

---

### Step 3 — Prototype Development: Core Requirements

Build a rapid, functional web application prototype (using your framework of choice, such as Streamlit, Dash, Shiny, Gradio, React/Next.js, FastAPI + modern frontend, etc.).

Your prototype should feature:

1. **Modern, Immersive UI/UX & Dynamic Visualizations**:

   - Move beyond traditional static tables.
   - Provide an intuitive, visually polished interface suited for diverse audiences worldwide.
   - Include interactive visual elements (charts, comparative metrics, breakdowns by region/country/thematic outcome area).
2. **LLM-Powered Natural Language Analytics Interface**:

   - Embed an interactive query interface where users can ask questions in plain natural language about the WBG Results data (e.g., *"Which regions made the most progress in digital access in recent years?"*, *"Compare outcome indicators across fragile and conflict-affected states"*, or *"What are the top 3 lagging indicators in climate resilience?"*).
   - The LLM must be integrated to query, filter, or reason over the underlying database (e.g., via Text-to-SQL/Pandas code generation, function calling / tool use, or structured RAG) and return **grounded, accurate analytical answers** rather than unverified hallucinations.
   - Wherever relevant, have the LLM summarize key trends and highlight quantitative findings.
3. **Model Choice & Technical Justification**:

   - You have complete autonomy in selecting which LLM model and provider to use (e.g., OpenAI GPT-4o / GPT-4o-mini, Anthropic Claude 3.5 Sonnet / Haiku, Google Gemini Flash, open-source models via Groq, Ollama, Hugging Face, etc.).
   - Provide a clear written justification of your model choice in your documentation (including any quick testing conducted, if applicable), addressing:
     - Accuracy and reasoning capabilities for structured data analysis.
     - Speed / latency considerations for a snappy user experience.
     - Cost efficiency and scalability.
     - Guardrails against hallucinated numbers or false data attribution.
   - **Note**: A well-reasoned, thoughtful model justification will be awarded additional points.

---

### Deliverables for Question 1:

1. **Source Code**: Fully runnable application code, with clear local setup and execution instructions in your README.
2. **Architecture & LLM Strategy Note** (in your report or README):
   - Diagram or concise description of the application architecture and data flow.
   - Detailed explanation of how the LLM interacts with the database (prompt design, tool calling / code execution, error handling).
   - Your model choice justification.
3. **Reproducibility & Visual Preview**:
   - **Plug-and-Play Setup**: The reviewing team will test and interact with your platform directly by plugging in our own API key / model endpoint. You must include a clear `.env.example` file documenting all required environment variables (e.g., `LLM_API_KEY`, `LLM_MODEL_NAME`, or custom endpoint URL) and 2–3 standard terminal commands in your README to run the application locally.
   - **Embedded Screenshots**: Embed 2–3 high-resolution screenshots directly in your repository README displaying the user interface layout and sample LLM query interactions for quick visual reference.
   - *(Optional)*: If you deploy your application to a free hosting service (e.g., Streamlit Community Cloud, Hugging Face Spaces, Vercel, etc.), you are welcome to provide a live URL as well.
4. **AI Coding Assistant Prompting Exchange**:
   - You are completely free to use any AI-assisted coding agent of your choice (e.g., GitHub Copilot, Claude Code, Cursor, Windsurf, Aider, ChatGPT, etc.) to develop this prototype.
   - **Mandatory**: You must export and include the **full prompting exchange / chat conversation history** between you and the AI coding assistant used during development (e.g., as Markdown, HTML, JSON, or text export files in your submission repository). **Failure to include the complete AI assistant chat conversations will result in a penalty and deduction of points in the assessment.**

---

## Question 2 — CPF-PAD Alignment Case Study: Uncertainty & Bias Analysis (50 Points)

### Context & Case Study Background

The World Bank Group prepares a **Country Partnership Framework (CPF)** for each client country. The CPF defines outcome areas — high-level strategic goals the Bank aims to support in that country (e.g., improving fiscal sustainability, expanding access to quality education). Individual **Projects** are appraised in **Project Appraisal Documents (PADs)**, which describe the project's objectives, components, expected outcomes, and design rationale.

A key question for the institution is: **how well are our projects aligned with country-level strategic goals as outlined in the partnership framework?**

To explore automated alignment scoring at scale, the team previously implemented a pilot assessment pipeline using a state-of-the-art Large Language Model (LLM).

#### The Pilot Setup & Methodology

- **Inputs**:
  - 4 CPF outcome area descriptions from a country partnership framework (`CPF 1: Fiscal Management & Governance`, `CPF 2: Climate-Resilient Agriculture`, `CPF 3: Human Capital & Primary Education`, `CPF 4: Digital Infrastructure & Financial Inclusion`).
  - 4 Project Appraisal Document (PAD) extracts describing project components and planned activities (`PAD A: Public Sector Modernization`, `PAD B: Rural Irrigation & Agri-tech`, `PAD C: Basic Education Reform`, `PAD D: Broadband Connectivity & SME Digital Payments`).
- **Prompting & Scoring Strategy**: A rubric-guided zero-shot prompt instructed the model to evaluate how well each project aligns with each CPF outcome area on a scale from **1 (No Alignment)** to **5 (Strong Direct Alignment)**, accompanied by a brief rationale.
- **Pilot Results (Baseline Alignment Matrix)**:

| Project (PAD)                    | CPF 1: Fiscal & Governance | CPF 2: Climate Agriculture | CPF 3: Education | CPF 4: Digital & Finance |
| :------------------------------- | :------------------------: | :------------------------: | :--------------: | :----------------------: |
| **PAD A (Public Sector)**        |          **4.6**           |            1.2             |       2.1        |           3.8            |
| **PAD B (Rural Irrigation)**     |            2.0             |          **4.8**           |       1.5        |           2.4            |
| **PAD C (Education Reform)**     |            1.8             |            1.1             |     **4.9**      |           2.2            |
| **PAD D (Broadband & Payments)** |            3.1             |            1.9             |       2.0        |         **4.7**          |

The pilot produced deterministic single-point estimates. Before this approach can be adopted for operational decision-making, senior leadership requires a critical methodological assessment focusing on **measurement uncertainty** and **potential systematic biases**.

*(Note: You do **not** need to build or run an LLM evaluation pipeline for this question. Treat the setup and baseline matrix above as the given case study for your analysis.)*

---

### Part A — Uncertainty Quantification Framework

LLM-generated scores are single point estimates. A score of `3.8` or `4.6` gives decision-makers no visibility into model confidence, prompt sensitivity, or borderline ambiguity.

**Develop a methodology to quantify uncertainty for this alignment scoring system.** There is no single correct approach — we want to evaluate your technical and conceptual reasoning.

Your response should address:

1. **Proposed Uncertainty Method**: Detail a concrete approach to quantify uncertainty for each cell in the alignment matrix (e.g., temperature/sampling self-consistency, prompt paraphrasing/perturbation, multi-model consensus, token log-probability / confidence metrics, or conformal prediction).
2. **Methodological Rationale**: Explain *why* your proposed method captures meaningful semantic and measurement uncertainty rather than trivial token-level noise.
3. **LLM Uncertainty vs. Traditional Statistical Models**: Discuss the specific challenges and nuances of measuring uncertainty in LLM-generated evaluative scores compared to traditional econometric or statistical estimators.
4. **Communication to Leadership**: How would you present these uncertainty metrics to senior leaders to help them distinguish between high-confidence alignments and borderline or ambiguous cases?

---

### Part B — Verbosity Bias Investigation

A colleague raises a concern:

> *"This scoring approach might create an incentive for project teams to write longer, more verbose PADs. If longer documents score higher simply because they contain more text, we'd be rewarding administrative bloat rather than genuine alignment."*

Investigate this concern and propose an experimental safeguard:

1. **Develop a hypothesis** about whether and why document length or syntactic verbosity might (or might not) bias LLM-based alignment scoring.
2. **Design an experimental procedure / test** to investigate your hypothesis (explain the experimental setup, manipulation of documents—e.g., text truncation, summarization, synthetic padding—and the evaluation metrics you would use).
3. **Write an executive narrative report** (2–3 paragraphs) presenting your reasoning, potential risks, and concrete recommendations for pipeline guardrails (e.g., length normalization, extraction filters, rubric constraints). This report should be written for a technically literate senior leader (e.g., a lead economist or policy manager).

---

## Question 3 — Scorecard Analytics & Executive Slide Deck (50 Points)

### Context

Beyond public communications on the external website of the WBG Scorecard, senior leadership needs to use the data for managerial purposes—tracking institutional results, identifying operational bottlenecks, allocating resources strategically, and conducting high-level stocktakes to guide decision-making.

In addition to the WBG Corporate Scorecard ([https://scorecard.worldbank.org](https://scorecard.worldbank.org)), you may also draw on other publicly available World Bank data sources for individual projects (such as the [Documents & Reports API](https://documents.worldbank.org)) or more generally the [World Bank Open Data API](https://data.worldbank.org) — if they help strengthen your narrative (not required, however).

### Part A — Data Pipeline

Build a **reproducible data pipeline** that:

1. Pulls data from the WBG Corporate Scorecard (via its API, data downloads, or whatever access method you identify).
2. Ingests, cleans, and structures the data for analysis.
3. Is documented well enough that someone else on the team could run it.

You are free to choose any area or tier of the Scorecard. Your pipeline should be robust and handle the data as-is (don't assume it will be clean).

### Part B — Executive Slide Deck

Imagine you are preparing a **3-slide stocktake** for the Managing Director and other senior leaders. Pick **one area** of the Scorecard and tell the story of how the Bank is performing.

Your 3 slides should:

- Present a clear, data-driven narrative.
- Be visually polished and appropriate for a senior, non-technical audience.
- Include at least one well-designed chart or visualization.
- Address the following question:

> Based on the Scorecard data and the Bank's current operational footprint, which areas and countries would you suggest prioritizing in a three-year plan for your chosen thematic area? What does the data tell us about where the biggest gaps or opportunities are?

You may use any tool to produce the slides (PowerPoint, Python-pptx, Quarto, LaTeX Beamer, Canva, Google Slides, etc.). Include the final slides as a PDF or HTML in your submission.

---

## Submission Requirements

Submit a single **`.zip` file** named `firstname_lastname_assessment.zip` containing your full replication package.

Unless explicitly labeled *(Optional)*, listed items are required for the questions you choose to complete. You are required to complete at least two questions; you are not required to complete all three.

### Your submission must include:

1. **A top-level `README.md`** specifying which questions you prioritized/completed, along with clear setup and execution instructions for your code.
2. **All source code**, organized in a clean directory structure (e.g., `q1_prototype/`, `q2_case_study/`, `q3_scorecard_deck/`).
3. **Deliverables and outputs for your completed questions (minimum 2)**:

   - **For Question 1 (Web Prototype)**:
     - Fully runnable application source code with plug-and-play local execution instructions.
     - `.env.example` template for the reviewing team to plug in an API key/endpoint.
     - Architecture, LLM integration design, and model choice justification write-up.
     - 2–3 high-resolution screenshots embedded in the README showing the UI and sample LLM query interactions.
     - *(Optional)* Live hosted link if deployed.
   - **For Question 2 (Uncertainty & Bias Case Study)**:
     - Uncertainty quantification framework write-up (Q2A).
     - Verbosity bias hypothesis, experimental test design, and executive advisory note (Q2B).
       *(Can be submitted as Markdown, Jupyter Notebook, or PDF).*
   - **For Question 3 (Scorecard Analytics & Slide Deck)**:
     - Reproducible Scorecard data pipeline code and documentation (Q3A).
     - Executive 3-slide deck (Q3B) — as a PDF or HTML.
4. **Environment specification**: `requirements.txt`, `environment.yml`, `package.json`, `pyproject.toml`, or equivalent — so we can recreate your environment.
5. **Data**: Include the raw data extracts or scripts/API instructions used to fetch the data for Questions 1 and 3.
6. **Full AI Coding Assistant Prompting Logs / Chat History**: If you used any AI-assisted coding agent or tool (such as GitHub Copilot, Claude Code, Cursor, Windsurf, Aider, ChatGPT, etc.) during the development of your prototype or code, you **must include the complete, unedited prompting exchanges and chat conversation transcripts** in your repository (e.g., saved in a `chat_logs/` or `ai_prompts/` folder). **Submissions that fail to provide these chat logs will incur a penalty and deduction of points.**

### What we value in submissions:

- **Innovation & Technical Judgment**: Thoughtful integration of LLM technologies into an intuitive, functional web interface, with well-argued model and architecture choices.
- **Analytical & Methodological Rigor**: Depth of reasoning in handling LLM uncertainty, measurement error, and verbosity bias.
- **Communication Quality**: The executive advisory notes, architectural documentation, and slide deck are as critical as the code.
- **Clean, Modular Code**: Well-organized, readable, reproducible code with sensible structure and documentation.
- **Transparency in AI Collaboration**: Clear documentation and unedited logs of how you guided, prompted, and steered your AI coding assistant.

### What you may use:

- Any programming language (Python or R preferred).
- Any LLM API (OpenAI, Anthropic, Google, open-source models, etc.). If you use a paid API, that is fine — we are evaluating your approach, not your budget.
- Any libraries, frameworks, or tools you find useful.
- AI coding assistants (GitHub Copilot, Claude Code, Cursor, Windsurf, ChatGPT Codex, etc.) are permitted and encouraged. We are evaluating your judgment, design decisions, prompt engineering, and analytical reasoning. However, **you must include the complete chat conversation history in your submission — omitting it will result in point deductions.**

---

*Good luck. We look forward to reviewing your work.*
