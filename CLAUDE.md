## 1. Project mission

We are participating in **SOCAR Hackathon 2026**, whose published theme is **“Intelligent Well Performance Analysis.”** The event is a two-day data-science hackathon organised by SOCAR and Caspian AI Institute. Teams (up to three people) are expected to build and present an **interactive engineering application** that connects:

1. operational / field data,
2. prediction or estimation of important variables, and
3. assessment of well and reservoir performance.

The intended outcome is a coherent engineering workflow that helps users move from data to predictions to engineering insight—not merely a notebook, isolated model, or generic chatbot.

**Important uncertainty:** The organisers explicitly say that the detailed challenge tasks will be revealed during the hackathon and that all teams will receive the same datasets and work under equal conditions. Do not assume the exact target variable, file formats, dataset schema, or scoring metric before the official briefing.

## 2. Event constraints and rules

- Each team may submit only one product.
- The jury evaluates a prototype presentation; build for a demonstrable end-to-end workflow.

Official event page: https://hackathon.socar.az/#overview

## 3. What the challenge is really about

The organisers describe a common subsurface/production engineering problem: direct measurement of subsurface conditions is rarely possible. Engineers therefore use continuous operational data and periodic measurements to estimate or predict key variables. In practice, this work can be fragmented across tools, scripts, and spreadsheets.

The prototype should bring the process into one workflow:

**Field/operational data → data validation and preparation → estimation/prediction → well/reservoir performance assessment → interpretable engineering insight.**

The exact workflow will depend on the revealed dataset and task. Keep the application modular so the model, target, and visualisations can be changed quickly.

## 4. Partner context and what it signals

### 4.1 SOCAR — operational domain and challenge owner

The hackathon is explicitly grounded in oil and gas production and geoscience. Optimise for engineering usefulness: reliable data handling, understandable predictions, useful diagnostics, and clear communication of uncertainty. A technically impressive model is not enough if an engineer cannot understand or act on its output.

### 4.2 Caspian AI Institute — applied AI for energy

Caspian AI describes its mission as turning complex data into actionable intelligence and investing in ventures that apply advanced technology to energy challenges.

Its public ventures provide useful examples of the institute's applied-AI philosophy:

- **Seismic AI:** AI-assisted seismic processing and quality control. The published workflow ingests raw geophysical data, structures it, scores data quality / risk, and flags cases for expert review. It emphasises explainability, visibility into decisions, integration with established tools, and keeping experts in control.
- **Methane AI:** A connected operational intelligence workflow: baseline measurements, ingest and validate multiple data sources, reconcile measurements against asset topology, visualise results, forecast emerging issues, prioritise interventions, and report transparently.
- **AutonomousLab AI:** AI-driven scientific discovery, prediction of material properties, confidence assessment, and validation. The broader lesson is to connect predictions to validation and real-world utility.

**Implication for our prototype:** favour applied AI with traceable data, confidence/uncertainty, human review, and a clear operational decision path. Do not add an LLM merely for novelty.

Caspian AI: https://caspian-ai.com/
Seismic AI: https://caspian-ai.com/seismic-ai 
Methane AI: https://caspian-ai.com/methane-ai 
AutonomousLab AI: https://caspian-ai.com/autonomouslab-ai

### 4.3 SOCAR Tech — enterprise and industrial technology expectations

SOCAR Tech describes itself as SOCAR's digital transformation arm. Its published capabilities and examples are especially relevant to the hackathon:

- **Industrial data platform / Lakehouse:** combines seismic, reservoir, well, financial, emissions, and operational data; supports batch and real-time ingestion, analytics, ML, and AI workloads.
- **Data governance:** data ownership, quality, lineage, security, retention, and accountability.
- **Operational dashboards:** interactive filtering and drill-down, KPI tracking, trend/anomaly visibility, and automated reporting.
- **Oil pump pattern analysis (dynamogram classification):** classifies pump operating states from well-curve shape and statistical features, including gas interference, valve leakage, sucker-rod breaks, and insufficient liquid supply; produces reports and abnormal-condition alerts with confidence scores.
- **Daily drilling report extraction:** transforms messy/unstructured Excel reports into structured, unified data.
- **First-break-picking QC automation:** AI-assisted geophysical quality control that flags potentially problematic seismic data while retaining expert oversight.
- **Rig scheduling and industrial digital twins:** actual-vs-planned tracking, early warnings, readiness assessment, simulation, and predictive decision support.

**Implication for our prototype:** demonstrate the habits of production-grade industrial software even if the deliverable is a short-lived prototype: clean data contracts, validation, clear error states, useful dashboards, reproducibility, and secure handling of data.

SOCAR Tech: https://socartech.az/ 
Data, Analytics & AI: https://socartech.az/en/services/data-management 
Industrial Digitalization & Energy Technology: https://socartech.az/en/services/operational-technologies

---

## 5. Product principles

Prioritise these principles unless the official task says otherwise:

1. **Engineer-first UX.** Use the language of wells, production, operating conditions, measurements, and performance. Make the main workflow obvious.
2. **One connected workflow.** A user should be able to load data, inspect data quality, run analysis, and understand the result in one application.
3. **Prediction plus interpretation.** Show what the model predicts and why the result matters operationally. Separate model output from engineering interpretation.
4. **Uncertainty and trust.** Show confidence intervals, prediction ranges, quality flags, or confidence scores where defensible. Never invent confidence values.
5. **Human-in-the-loop.** Flag questionable records and high-risk predictions for review. Do not present the model as an unquestionable authority.
6. **Data quality before modelling.** Detect missing values, duplicates, invalid ranges, inconsistent units, time gaps, and suspicious outliers. Preserve raw data and make transformations visible.
7. **Fast and robust demo.** The core workflow must work locally and reliably with the supplied data. Avoid unnecessary infrastructure and external dependencies.
8. **Evidence over hype.** Report the evaluation method and metrics honestly. Compare against a simple baseline. Avoid unsupported claims about production impact.
9. **Security and data locality.** Treat hackathon datasets as confidential. Do not upload them to public services, external LLMs, public repositories, or third-party APIs. Do not include raw dataset rows in logs or screenshots shared externally.
10. **Explainable outputs.** Every chart, metric, alert, and recommendation should have a clear definition and provenance.

## 6. Flexible technical approach

Do not lock into a model or schema until the task and data are revealed. Once they are available, follow this sequence:

### A. Inspect the data

- Inventory files, sheets, tables, columns, data types, units, row counts, and time coverage.
- Identify the entity/granularity: well, well-test, sensor, time interval, reservoir, or another level.
- Determine target variable(s), input features, timestamps, identifiers, and available metadata.
- Check missingness, duplicates, impossible values, inconsistent units, irregular sampling, and outliers.
- Check for target leakage, especially features recorded after the prediction time.
- Split train/validation/test data in a way that reflects deployment. For time-dependent data, prefer chronological splits; consider well/group splits to test generalisation to unseen wells.
- Keep an untouched test set if the task provides one.

### B. Establish a baseline

Start with a simple, defensible baseline before complex models. Choose based on the task:

- Regression / forecasting: mean or median baseline, persistence / last-value baseline for time series, then tree-based models such as Random Forest or gradient boosting.
- Classification / fault detection: majority-class baseline, then a tree-based classifier; handle class imbalance and report per-class metrics.
- Anomaly detection: transparent statistical thresholds or robust methods as a baseline.
- Clustering / segmentation: scale appropriate features, justify the distance/cluster method, and show whether the segments are operationally meaningful.

Use only methods supported by the actual data volume and time available. Avoid deep learning unless it has a clear advantage and can be validated within the hackathon.

### C. Evaluate correctly

Choose metrics based on the actual task, not convenience:

- Regression: MAE, RMSE, and optionally R²; explain the units and business meaning of error.
- Classification: precision, recall, F1, confusion matrix, and PR-AUC/ROC-AUC where appropriate. For safety- or failure-related classes, discuss false negatives explicitly.
- Forecasting: evaluate by forecast horizon and use a time-aware split.
- Anomaly detection: assess alert usefulness and false-alarm burden if labels permit.

Always compare with the baseline. Check performance by well, operating regime, and time period where possible. Do not claim generalisation beyond the validation design.

### D. Turn outputs into engineering insight

Depending on the data and task, useful outputs may include:

- actual vs predicted values over time;
- well-level performance summaries and rankings;
- deviations from expected performance;
- anomaly / abnormal operating-condition flags;
- contributing features or interpretable drivers;
- prediction intervals or uncertainty bands;
- data-quality warnings;
- prioritised wells or cases for engineer review.

Only implement outputs that can be justified by the supplied dataset and task. Do not invent physical interpretations or causal claims from correlations.

### E. Build a focused interface

A practical prototype can have these views (adapt after the task is revealed):

1. **Overview:** dataset status, key KPIs, number of wells/records analysed, high-priority cases.
2. **Data explorer:** filters by well/time/field, raw and cleaned data preview, missingness and quality indicators.
3. **Analysis:** model selection/configuration only if useful, run status, validation metrics, baseline comparison.
4. **Well detail:** time-series plots, measured vs predicted values, operating context, alerts, uncertainty, and explanation.
5. **Recommendations / review queue:** prioritised cases with reason, severity, evidence, and human review status.

The UI should be simple enough to finish and rehearse in two days. A polished, reliable narrow workflow is better than a broad unfinished platform.

---

## 7. Suggested implementation architecture

Use the team's existing stack if one already exists. Otherwise, choose the fastest maintainable local stack. A reasonable default is:

- **Python** for data processing and modelling (`pandas`, `numpy`, `scikit-learn`; add specialised libraries only when required).
- **Streamlit** for a rapid interactive prototype, or the team's existing frontend framework if already established.
- Keep processing, modelling, evaluation, and UI logic separate.
- Store configuration and feature definitions explicitly; avoid hard-coded column assumptions.
- Save model artefacts and evaluation results locally where useful.
- Provide a deterministic demo path using the supplied dataset.

Possible structure (adapt to the actual repository):

```text
project/
├── CLAUDE.md                 # This project context
├── README.md                 # Setup and demo instructions
├── app/                      # UI / application entry point
├── src/
│   ├── data/                  # Loading, validation, preprocessing
│   ├── features/              # Feature engineering
│   ├── models/                # Baselines and candidate models
│   ├── evaluation/            # Splits, metrics, validation
│   └── insights/              # Explanations and engineering summaries
├── tests/                     # Data and model tests
├── artifacts/                 # Local model/evaluation outputs (not raw confidential data)
└── requirements.txt
```

Keep raw hackathon data out of version control. Add data directories and generated sensitive artefacts to `.gitignore`.

## 8. How Claude should work with the team

- First inspect the repository, existing code, and actual dataset. Do not assume this is a greenfield project.
- Ask for or inspect the official challenge statement before proposing a specific target/model.
- When data is provided, profile it before writing modelling code. Show the team what each column means if metadata is available; do not guess units.
- Explain domain concepts and modelling decisions clearly. The team may include software/data-science members who are not petroleum or reservoir specialists.
- Prefer small, testable increments. Make the smallest working end-to-end slice first.
- Do not silently fabricate sample data, domain rules, physical equations, units, or performance numbers. If a demo fixture is necessary, label it clearly as synthetic.
- Do not leak dataset content into web searches, public APIs, external AI tools, telemetry, or public code repositories.
- Keep code readable and demo-ready. Include setup commands and a concise explanation of changed files.
- When uncertain, list assumptions and ask a focused question rather than building on an unsupported assumption.
- Preserve the ability to swap target variables, models, and visualisations after the task briefing.

## 9. Two-day execution strategy

### Before / immediately after briefing

- Prepare the local environment and confirm the app can run.
- Read the official task statement carefully; extract target, constraints, input files, expected outputs, and evaluation criteria.
- Inspect the supplied data and agree on a shared understanding of columns and units.
- Assign clear roles: data/domain interpretation, modelling/evaluation, and application/demo (roles can overlap in a small team).

### Build phase

1. Get a working data loader and data-quality report.
2. Produce a baseline and valid evaluation split.
3. Train and evaluate one credible model.
4. Connect its output to one useful well-level or dataset-level visualisation.
5. Add a small number of defensible engineering insights and review flags.
6. Test the complete path from app start to final result.

### Final hours

- Freeze scope; stop adding speculative features.
- Re-run the complete workflow from a clean start.
- Prepare a demo dataset path and a fallback screenshot/video only if event rules permit.
- Rehearse a short story: problem → data → method → result → engineering value → limitations.
- Clearly disclose assumptions, validation method, model limitations, and what would be needed for production deployment.

## 10. Demo / jury narrative

A strong presentation should answer:

1. **Problem:** What engineering decision or workflow are we helping with?
2. **Data:** What data did we receive, what does it represent, and how did we validate it?
3. **Method:** What baseline and model did we use, and why?
4. **Evidence:** How well does it perform on a valid holdout set compared with the baseline?
5. **Workflow:** How does an engineer use the application from input to insight?
6. **Actionability:** What can the engineer investigate or prioritise based on the result?
7. **Trust:** How are uncertainty, data quality, and human review handled?
8. **Limitations:** What cannot yet be concluded, and what would be required before operational use?

Do not claim the prototype is production-ready. Position it as a proof of concept that could be hardened through domain validation, integration, security review, and operational testing.

---

## 11. Open questions to resolve at the event

- What is the exact task statement and expected deliverable?
- Which target variable(s) must be estimated or predicted?
- What are the data sources, schemas, units, sampling rates, and entity identifiers?
- Are there known engineering equations, reference values, or domain constraints participants should use?
- Is the task regression, forecasting, classification, anomaly detection, optimisation, or a combination?
- What evaluation metric and validation protocol will the jury use?
- Are external libraries, pretrained models, internet access, or external APIs restricted?
- Must the prototype run offline or on a specific machine/environment?
- What level of interpretability or engineering explanation is expected?
- Are there requirements for persistence, export, or integration with existing tools?

Until these are answered, treat all proposed model targets and UI screens as adaptable options, not confirmed requirements.

## 12. Sources reviewed

The following are the primary public sources used to create this context:

1. SOCAR Hackathon 2026 — overview, theme, dates, rules, and challenge framing: https://hackathon.socar.az/#overview
2. Caspian AI Institute — mission and ventures: https://caspian-ai.com/
3. Caspian AI — Seismic AI: https://caspian-ai.com/seismic-ai
4. Caspian AI — Methane AI: https://caspian-ai.com/methane-ai
5. Caspian AI — AutonomousLab AI: https://caspian-ai.com/autonomouslab-ai
6. SOCAR Tech — Data, Analytics & Artificial Intelligence: https://socartech.az/en/services/data-management
7. SOCAR Tech — Industrial Digitalization & Energy Technology: https://socartech.az/en/services/operational-technologies

**Source hierarchy:** If this file conflicts with the official challenge briefing, mentor guidance, dataset documentation, or event rules, follow the official event materials. Partner websites are used here to infer the broader industrial context, not to claim that every listed partner technology is part of this specific challenge.
