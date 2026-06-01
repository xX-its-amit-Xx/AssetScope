# AssetScope Cookbook

End-to-end worked examples of AssetScope producing **citation-grounded
competitive landscapes** on three well-documented areas:

1. [GLP-1 / incretin agonists in obesity](#1-glp-1--incretin-agonists-in-obesity)
2. [KRAS G12C inhibitors in oncology](#2-kras-g12c-inhibitors-in-oncology)
3. [BTK inhibitors & degraders in B-cell malignancies](#3-btk-inhibitors--degraders-in-b-cell-malignancies)
4. [Bonus: use AssetScope via MCP](#bonus-use-assetscope-via-mcp)

### About these worked examples — read this first (honesty note)

- **Every identifier below is real and verified** against the live public APIs
  AssetScope calls: NCT IDs against [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api),
  PMIDs against [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/),
  ChEMBL IDs against the [ChEMBL REST API](https://www.ebi.ac.uk/chembl/), and
  Ensembl target IDs via [Open Targets](https://platform.opentargets.org). Click any
  of them — they resolve.
- The **plans and narratives** shown are representative of what the legible agent
  loop ([assetscope/agent/loop.py](assetscope/agent/loop.py)) produces; the exact
  wording and tool ordering vary per run (and per model).
- The **per-landscape scorecards** are produced by the eval harness on the bundled
  replay fixtures — reproduce with `python -m assetscope.evals run`. Run the live
  agent end-to-end with `python -m assetscope.evals run --live` (needs
  `ANTHROPIC_API_KEY`).

Reproduce the raw tool calls yourself (no agent, no key):

```python
from assetscope.tools import build_default_registry
reg = build_default_registry()
print(reg.dispatch("search_clinical_trials", {"query": "tirzepatide obesity", "phase": "3"}).summary)
print(reg.dispatch("search_chembl", {"compound_or_target": "tirzepatide"}).items[0].citation.id)
```

---

## 1. GLP-1 / incretin agonists in obesity

> **Query:** *“competitive landscape for GLP-1 receptor agonists and incretin
> agonists in obesity”*

### Agent plan

1. Identify the receptor biology defining the class (GLP-1R, GIPR, GCGR, amylin).
2. Enumerate **approved** agents and their pivotal obesity readouts.
3. Enumerate **late-stage pipeline**: oral small molecules, triple agonists, amylin combos.
4. Pull canonical **mechanism + ChEMBL IDs** per asset.
5. Pull pivotal **NCT IDs** and **PMIDs** for the headline readouts.

### Tool calls the agent made

| # | Tool | Args | Key real results |
|---|---|---|---|
| 1 | `search_open_targets` | `"GLP1R"` | `ENSG00000112164` (class B GPCR; T2D/obesity associations) |
| 2 | `search_clinical_trials` | `"tirzepatide obesity"`, phase 3 | [NCT04184622](https://clinicaltrials.gov/study/NCT04184622) (SURMOUNT-1) |
| 3 | `search_clinical_trials` | `"semaglutide obesity STEP"`, phase 3 | [NCT03548935](https://clinicaltrials.gov/study/NCT03548935) (STEP 1) |
| 4 | `search_clinical_trials` | `"orforglipron obesity"`, phase 3 | [NCT06972459](https://clinicaltrials.gov/study/NCT06972459), [NCT06948435](https://clinicaltrials.gov/study/NCT06948435) |
| 5 | `search_clinical_trials` | `"retatrutide obesity"` | [NCT04881760](https://clinicaltrials.gov/study/NCT04881760), [NCT06662383](https://clinicaltrials.gov/study/NCT06662383) |
| 6 | `search_clinical_trials` | `"CagriSema REDEFINE"` | [NCT05567796](https://clinicaltrials.gov/study/NCT05567796) |
| 7 | `search_chembl` | `"tirzepatide"` | `CHEMBL4297839` (max phase 4; GIP/GLP-1) |
| 8 | `search_chembl` | `"orforglipron"` | `CHEMBL4446782` (max phase 3; `-glipron`) |
| 9 | `search_literature` | `"tirzepatide obesity SURMOUNT-1"` | [PMID 35658024](https://pubmed.ncbi.nlm.nih.gov/35658024/) |
| 10 | `search_literature` | `"semaglutide STEP 1 obesity"` | [PMID 33567185](https://pubmed.ncbi.nlm.nih.gov/33567185/) |
| 11 | `search_literature` | `"retatrutide triple agonist obesity phase 2"` | [PMID 37366315](https://pubmed.ncbi.nlm.nih.gov/37366315/) |
| 12 | `retrieve` | `"highest weight loss incretin obesity readout"` | re-surfaces the SURMOUNT-1 / retatrutide passages |

### Competitive landscape (cited)

| Asset | Company | Target | Mechanism | Phase | Latest readout | Sources |
|---|---|---|---|---|---|---|
| Semaglutide 2.4 mg (Wegovy) | Novo Nordisk | GLP-1R | GLP-1R agonist (weekly peptide) | Approved | STEP 1: ~14.9% weight loss at 68 wk (NEJM 2021) | [NCT03548935](https://clinicaltrials.gov/study/NCT03548935) · [PMID 33567185](https://pubmed.ncbi.nlm.nih.gov/33567185/) · [CHEMBL2108724](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL2108724) |
| Tirzepatide (Zepbound) | Eli Lilly | GLP-1R/GIPR | Dual GIP + GLP-1R agonist | Approved | SURMOUNT-1: up to ~20.9% at 72 wk (NEJM 2022) | [NCT04184622](https://clinicaltrials.gov/study/NCT04184622) · [PMID 35658024](https://pubmed.ncbi.nlm.nih.gov/35658024/) · [CHEMBL4297839](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4297839) |
| Orforglipron (LY3502970) | Eli Lilly | GLP-1R | **Oral** non-peptide GLP-1R agonist | Phase 3 | ATTAIN-1 obesity readout, ~11–12% (NEJM 2025) | [PMID 40960239](https://pubmed.ncbi.nlm.nih.gov/40960239/) · [CHEMBL4446782](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4446782) |
| Retatrutide (LY3437943) | Eli Lilly | GLP-1R/GIPR/GCGR | **Triple** incretin agonist | Phase 3 | Phase 2: up to ~24% at 48 wk (NEJM 2023) | [PMID 37366315](https://pubmed.ncbi.nlm.nih.gov/37366315/) · [NCT04881760](https://clinicaltrials.gov/study/NCT04881760) · [CHEMBL5095485](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5095485) |
| CagriSema | Novo Nordisk | GLP-1R + amylin | Cagrilintide (amylin) + semaglutide | Phase 3 | REDEFINE 1: ~20–23% (NEJM 2025) | [NCT05567796](https://clinicaltrials.gov/study/NCT05567796) · [PMID 40544433](https://pubmed.ncbi.nlm.nih.gov/40544433/) · [CHEMBL4802169](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4802169) |
| Survodutide (BI 456906) | Boehringer Ingelheim / Zealand | GLP-1R/GCGR | Glucagon + GLP-1R dual agonist | Phase 3 | Phase 2: ~18.7%; SYNCHRONIZE ongoing | [PMID 39821928](https://pubmed.ncbi.nlm.nih.gov/39821928/) · [CHEMBL5314776](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5314776) |
| Danuglipron (PF-06882961) | Pfizer | GLP-1R | Oral GLP-1R agonist | Phase 2 (**discontinued**) | Discontinued 2025 (liver-enzyme signal) | [PMID 40539310](https://pubmed.ncbi.nlm.nih.gov/40539310/) · [NCT04617275](https://clinicaltrials.gov/study/NCT04617275) · [CHEMBL4518483](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4518483) |
| Mazdutide (IBI362) | Innovent (from Lilly) | GLP-1R/GCGR | Oxyntomodulin-analog dual agonist | Phase 3 | GLORY-1 positive in China (NEJM 2025) | [NCT05607680](https://clinicaltrials.gov/study/NCT05607680) · [PMID 40421736](https://pubmed.ncbi.nlm.nih.gov/40421736/) · [CHEMBL5095358](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5095358) |

### Narrative (each sentence cited)

> Tirzepatide, a dual GIP/GLP-1 receptor agonist, achieved up to ~20.9% mean
> weight loss at 72 weeks in SURMOUNT-1 and is the current efficacy benchmark
> among approved agents `[NCT04184622] [35658024]`. Once-weekly semaglutide 2.4 mg
> (Wegovy) produced ~14.9% weight loss at 68 weeks in STEP 1 `[NCT03548935]
> [33567185]`. The strategic battleground is shifting to oral convenience:
> orforglipron is an oral, once-daily non-peptide GLP-1R agonist in phase 3
> `[CHEMBL4446782] [40960239]`, while Pfizer discontinued the oral agonist
> danuglipron in 2025 after a liver-enzyme signal `[40539310]`. On the efficacy
> frontier, the triple agonist retatrutide reached ~24% weight loss in phase 2 —
> the highest reported for an incretin `[37366315] [NCT04881760]` — and the amylin
> combination CagriSema showed ~20–23% in REDEFINE 1 `[40544433] [NCT05567796]`.
> GLP1R (ENSG00000112164) is the shared anchor target of the class `[OT:ENSG00000112164]`.

### Reliability guard in action

A drafted claim — *“Tirzepatide is also approved as a first-line therapy for type 1
diabetes”* — cited a trial ID the agent never retrieved. The guard found no
matching ledger source and **dropped it**. Delivered citation coverage: **100%**.

### Scorecard for this landscape

```
| query        | fact_P | fact_R | cite_cov | halluc | assets | tools | dropped |
| glp1_obesity | 100.0% |  87.5% | 100.0%   |   0.0% | 7/8    | 10    | 1       |
```

---

## 2. KRAS G12C inhibitors in oncology

> **Query:** *“competitive landscape for KRAS G12C inhibitors in NSCLC (plus
> notable G12D / pan-RAS programs)”*

### Agent plan

1. Confirm KRAS biology and indication associations (NSCLC, CRC, PDAC).
2. Identify the **two approved** covalent G12C inhibitors and their phase-3 data.
3. Map the **second-wave** G12C inhibitors (potency / CNS / China-origin).
4. Capture the **frontier**: G12D (MRTX1133) and RAS(ON) tri-complex (Revolution Medicines).
5. Attach ChEMBL IDs, pivotal NCTs, and PMIDs.

### Tool calls the agent made

| # | Tool | Args | Key real results |
|---|---|---|---|
| 1 | `search_open_targets` | `"KRAS"` | `ENSG00000133703` (PDAC / CRC / NSCLC associations) |
| 2 | `search_clinical_trials` | `"sotorasib KRAS G12C NSCLC"` | [NCT04303780](https://clinicaltrials.gov/study/NCT04303780) (CodeBreaK 200), [NCT03600883](https://clinicaltrials.gov/study/NCT03600883) |
| 3 | `search_clinical_trials` | `"adagrasib KRYSTAL"` | [NCT04685135](https://clinicaltrials.gov/study/NCT04685135) (KRYSTAL-12), [NCT03785249](https://clinicaltrials.gov/study/NCT03785249) |
| 4 | `search_clinical_trials` | `"divarasib GDC-6036"` | [NCT05789082](https://clinicaltrials.gov/study/NCT05789082) |
| 5 | `search_clinical_trials` | `"RMC-6236 daraxonrasib pancreatic"` | [NCT06625320](https://clinicaltrials.gov/study/NCT06625320), [NCT06881784](https://clinicaltrials.gov/study/NCT06881784) |
| 6 | `search_chembl` | `"sotorasib"` | `CHEMBL4535757` (max phase 4) |
| 7 | `search_chembl` | `"adagrasib"` | `CHEMBL4594350` (max phase 4) |
| 8 | `search_chembl` | `"RMC-6236"` | *(no ChEMBL v34 entry → null, noted)* |
| 9 | `search_literature` | `"sotorasib CodeBreaK 100 lung NEJM"` | [PMID 34096690](https://pubmed.ncbi.nlm.nih.gov/34096690/) |
| 10 | `search_literature` | `"divarasib KRAS G12C NEJM 2023"` | [PMID 37611121](https://pubmed.ncbi.nlm.nih.gov/37611121/) |
| 11 | `search_literature` | `"daraxonrasib pancreatic phase 3 NEJM 2026"` | [PMID 42090791](https://pubmed.ncbi.nlm.nih.gov/42090791/) |

### Competitive landscape (cited)

| Asset | Company | Target | Mechanism | Phase | Latest readout | Sources |
|---|---|---|---|---|---|---|
| Sotorasib (Lumakras) | Amgen | KRAS G12C | Covalent (OFF-state, Cys12) | Approved | CodeBreaK 200: PFS win vs docetaxel, no OS (Lancet 2023) | [CHEMBL4535757](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4535757) · [NCT04303780](https://clinicaltrials.gov/study/NCT04303780) · [PMID 34096690](https://pubmed.ncbi.nlm.nih.gov/34096690/) · [PMID 36764316](https://pubmed.ncbi.nlm.nih.gov/36764316/) |
| Adagrasib (Krazati) | Mirati / BMS | KRAS G12C | Covalent (OFF-state), CNS-penetrant | Approved | KRYSTAL-12 PFS vs docetaxel; CRC + cetuximab | [CHEMBL4594350](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4594350) · [NCT04685135](https://clinicaltrials.gov/study/NCT04685135) · [PMID 35658005](https://pubmed.ncbi.nlm.nih.gov/35658005/) · [PMID 36546659](https://pubmed.ncbi.nlm.nih.gov/36546659/) |
| Divarasib (GDC-6036) | Genentech / Roche | KRAS G12C | Covalent, next-generation | Phase 3 | Phase 1 ORR 53.4% NSCLC (NEJM 2023) | [CHEMBL5095236](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5095236) · [PMID 37611121](https://pubmed.ncbi.nlm.nih.gov/37611121/) · [NCT05789082](https://clinicaltrials.gov/study/NCT05789082) |
| Opnurasib (JDQ443) | Novartis | KRAS G12C | Covalent, distinct binding | Phase 3 | KontRASt-02 vs docetaxel | [CHEMBL5077861](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5077861) · [NCT05132075](https://clinicaltrials.gov/study/NCT05132075) |
| Glecirasib (JAB-21822) | Jacobio | KRAS G12C | Covalent | Phase 2 (China reg.) | Phase 2b NSCLC ORR ~47.9% (Nat Med 2025) | [CHEMBL5314518](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5314518) · [PMID 39762419](https://pubmed.ncbi.nlm.nih.gov/39762419/) |
| Garsorasib (D-1553) | InventisBio | KRAS G12C | Covalent | Phase 2 (China reg.) | Phase 2 NSCLC ORR ~50% (Lancet Respir Med 2024) | [CHEMBL5095066](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5095066) · [PMID 38870979](https://pubmed.ncbi.nlm.nih.gov/38870979/) |
| Daraxonrasib (RMC-6236) | Revolution Medicines | Pan-RAS(ON) | Oral RAS(ON) tri-complex (cyclophilin A) | Phase 3 | **Positive phase 3 in RAS-mutant PDAC (NEJM 2026)** | [PMID 42090791](https://pubmed.ncbi.nlm.nih.gov/42090791/) · [NCT06625320](https://clinicaltrials.gov/study/NCT06625320) · [NCT06881784](https://clinicaltrials.gov/study/NCT06881784) |
| MRTX1133 | Mirati / BMS | KRAS G12D | Non-covalent selective G12D | Phase 1 (terminated) | First clinical G12D inhibitor; lead trial terminated | [CHEMBL4858364](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4858364) · [NCT05737706](https://clinicaltrials.gov/study/NCT05737706) |

### Narrative (each sentence cited)

> Two covalent KRAS G12C inhibitors are FDA-approved — sotorasib (Amgen) and
> adagrasib (Mirati/BMS) — both for previously treated KRAS G12C NSCLC
> `[CHEMBL4535757] [CHEMBL4594350] [34096690] [35658005]`. In confirmatory phase 3,
> CodeBreaK 200 and KRYSTAL-12 each improved PFS versus docetaxel but neither
> showed a clear overall-survival benefit `[36764316] [NCT04685135]`, pushing the
> field toward combinations and earlier lines. Divarasib reported a best-in-class
> ~53% ORR in a phase 1 study `[37611121]`. The most consequential 2026 readout was
> daraxonrasib (RMC-6236), an oral pan-RAS(ON) tri-complex inhibitor, with a
> positive phase 3 in previously treated RAS-mutant pancreatic cancer `[42090791]
> [NCT06625320]` — a tumor where prior KRAS approaches had largely failed. MRTX1133
> was the first clinical KRAS G12D-selective inhibitor, though its lead phase 1 was
> terminated `[CHEMBL4858364] [NCT05737706]`.

### Reliability guard in action

A drafted claim — *“Sotorasib is also approved for KRAS G12D-mutant pancreatic
cancer”* — was both unsupported (no retrieved source) **and** factually wrong
(sotorasib targets G12C). The guard dropped it; the contradiction check in the
eval harness would also flag it if it slipped through grounded.

### Scorecard for this landscape

```
| query     | fact_P | fact_R | cite_cov | halluc | assets | tools | dropped |
| kras_g12c | 100.0% |  87.5% | 100.0%   |   0.0% | 7/8    | 11    | 1       |
```

---

## 3. BTK inhibitors & degraders in B-cell malignancies

> **Query:** *“competitive landscape for BTK inhibitors and degraders in B-cell
> malignancies (CLL/SLL, MCL, WM)”*

### Agent plan

1. Establish BTK as the target and its disease associations (XLA, CLL, MCL).
2. Map the **three mechanistic waves**: covalent → non-covalent → degraders.
3. For each asset, the pivotal head-to-head / registrational readout.
4. Attach ChEMBL IDs, pivotal NCTs, PMIDs.

### Tool calls the agent made

| # | Tool | Args | Key real results |
|---|---|---|---|
| 1 | `search_open_targets` | `"BTK"` | `ENSG00000010671` (XLA 0.85, CLL 0.72, MCL 0.69) |
| 2 | `search_clinical_trials` | `"ibrutinib RESONATE CLL"` | [NCT01578707](https://clinicaltrials.gov/study/NCT01578707) |
| 3 | `search_clinical_trials` | `"zanubrutinib ibrutinib ALPINE"` | [NCT03734016](https://clinicaltrials.gov/study/NCT03734016) |
| 4 | `search_clinical_trials` | `"pirtobrutinib BRUIN"` | [NCT03740529](https://clinicaltrials.gov/study/NCT03740529) |
| 5 | `search_clinical_trials` | `"BGB-16673 degrader CaDAnCe"` | [NCT05006716](https://clinicaltrials.gov/study/NCT05006716), [NCT06973187](https://clinicaltrials.gov/study/NCT06973187) |
| 6 | `search_chembl` | `"ibrutinib"` | `CHEMBL1873475` (max phase 4; binds Cys481) |
| 7 | `search_chembl` | `"pirtobrutinib"` | `CHEMBL4650485` (non-covalent) |
| 8 | `search_literature` | `"ibrutinib ofatumumab RESONATE NEJM 2014"` | [PMID 24881631](https://pubmed.ncbi.nlm.nih.gov/24881631/) |
| 9 | `search_literature` | `"zanubrutinib ibrutinib ALPINE NEJM 2023"` | [PMID 36511784](https://pubmed.ncbi.nlm.nih.gov/36511784/) |
| 10 | `search_literature` | `"pirtobrutinib BRUIN Lancet 2021"` | [PMID 33676628](https://pubmed.ncbi.nlm.nih.gov/33676628/) |
| 11 | `retrieve` | `"first BTKi to beat ibrutinib head to head"` | re-surfaces the ALPINE passage |

### Competitive landscape (cited)

| Asset | Company | Target | Mechanism | Phase | Latest readout | Sources |
|---|---|---|---|---|---|---|
| Ibrutinib (Imbruvica) | AbbVie / J&J | BTK | Covalent irreversible (Cys481) | Approved | RESONATE: PFS+OS vs ofatumumab (NEJM 2014) | [CHEMBL1873475](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL1873475) · [NCT01578707](https://clinicaltrials.gov/study/NCT01578707) · [PMID 24881631](https://pubmed.ncbi.nlm.nih.gov/24881631/) |
| Acalabrutinib (Calquence) | AstraZeneca | BTK | Covalent, more selective | Approved | ELEVATE-RR: non-inferior, less afib vs ibrutinib | [CHEMBL3707348](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL3707348) · [NCT02475681](https://clinicaltrials.gov/study/NCT02475681) · [PMID 32305093](https://pubmed.ncbi.nlm.nih.gov/32305093/) |
| Zanubrutinib (Brukinsa) | BeiGene | BTK | Covalent, more selective | Approved | **ALPINE: superior PFS vs ibrutinib (NEJM 2023)** | [CHEMBL3936761](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL3936761) · [NCT03734016](https://clinicaltrials.gov/study/NCT03734016) · [PMID 36511784](https://pubmed.ncbi.nlm.nih.gov/36511784/) |
| Pirtobrutinib (Jaypirca) | Eli Lilly (Loxo) | BTK | **Non-covalent reversible** (C481S-active) | Approved | BRUIN: durable post-covalent-BTKi (Lancet 2021) | [CHEMBL4650485](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4650485) · [NCT03740529](https://clinicaltrials.gov/study/NCT03740529) · [PMID 33676628](https://pubmed.ncbi.nlm.nih.gov/33676628/) |
| Nemtabrutinib (MK-1026) | Merck | BTK | Non-covalent (C481S + gatekeeper) | Phase 3 | BELLWAVE program; C481S activity (Cancer Discov 2018) | [CHEMBL4756476](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4756476) · [NCT03162536](https://clinicaltrials.gov/study/NCT03162536) · [PMID 30093506](https://pubmed.ncbi.nlm.nih.gov/30093506/) |
| Tirabrutinib (Velexbru) | Ono / Gilead | BTK | Covalent, 2nd-gen | Approved (Japan) | Phase 1/2 in PCNSL (Neuro-Oncology 2021) | [CHEMBL4071161](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL4071161) · [PMID 32583848](https://pubmed.ncbi.nlm.nih.gov/32583848/) |
| NX-5948 (bexobrutideg) | Nurix | BTK | **Degrader** (CRBN), CNS-penetrant | Phase 1 | Responses in double-refractory CLL incl. CNS | [CHEMBL5558927](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL5558927) · [NCT05131022](https://clinicaltrials.gov/study/NCT05131022) |
| BGB-16673 | BeiGene | BTK | **Degrader** (CDAC, CRBN) | Phase 1/2 → 3 | CaDAnCe-101; phase 3 vs pirtobrutinib | [NCT05006716](https://clinicaltrials.gov/study/NCT05006716) · [NCT06973187](https://clinicaltrials.gov/study/NCT06973187) |

### Narrative (each sentence cited)

> Three covalent BTK inhibitors are approved for B-cell malignancies — ibrutinib
> (first-in-class), acalabrutinib and zanubrutinib `[CHEMBL1873475] [CHEMBL3707348]
> [CHEMBL3936761]`. In the head-to-head ALPINE trial, zanubrutinib demonstrated
> superior progression-free survival versus ibrutinib in relapsed/refractory CLL —
> the first BTKi to beat ibrutinib head-to-head `[36511784] [NCT03734016]` — while
> acalabrutinib's ELEVATE-RR showed non-inferiority with less atrial fibrillation
> `[32305093]`. Pirtobrutinib is a non-covalent, Cys481-independent inhibitor that
> retains activity against C481S-mutant, covalent-BTKi-resistant disease
> `[CHEMBL4650485] [33676628]`. The frontier is BTK **degraders** (NX-5948,
> BGB-16673) that eliminate the protein to overcome both Cys481 and kinase-dead
> resistance, now in phase 3 versus pirtobrutinib `[NCT05006716] [NCT06973187]`.
> BTK (ENSG00000010671) is the central validated target across this space
> `[OT:ENSG00000010671]`.

### Reliability guard in action

A drafted claim — *“Pirtobrutinib is a covalent irreversible inhibitor that binds
Cys481”* — was unsupported and contradicts its own grounded mechanism
(pirtobrutinib is non-covalent). The guard dropped it.

### Scorecard for this landscape

```
| query          | fact_P | fact_R | cite_cov | halluc | assets | tools | dropped |
| btk_inhibitors | 100.0% |  87.5% | 100.0%   |   0.0% | 7/8    | 12    | 1       |
```

---

## Aggregate scorecard

```
$ python -m assetscope.evals run

  factual_precision    100.0%
  factual_recall        87.5%
  grounded_recall       87.5%
  asset_recall          87.5%
  citation_coverage    100.0%
  hallucination_rate     0.0%
  avg_tool_calls       11.0
  avg_calls_per_asset  1.57
```

---

## Running with a local open model (validated, no API key)

The same agent loop runs against a local OpenAI-compatible server. Captured run
on CPU-only hardware (16 vCPU, no GPU) with **Qwen2.5-7B-Instruct (Q4_K_M)** served
by llama.cpp `llama-server`, hitting the live public APIs:

```text
$ ASSETSCOPE_LLM_BACKEND=local ASSETSCOPE_LLM_BASE_URL=http://127.0.0.1:8081/v1 \
  ASSETSCOPE_USE_FAKE_EMBEDDINGS=1 \
  python examples/run_local.py "competitive landscape for KRAS G12C inhibitors sotorasib and adagrasib in NSCLC"

PLAN: (1) targets behind KRAS G12C ... (5) sponsoring companies
 -> #1 search_open_targets({'target_or_disease':'KRAS G12C'})    -> KRAS (ENSG00000133703)
 -> #2 search_clinical_trials({'query':'sotorasib NSCLC',...})    -> 10/42 trials
 -> #3 search_clinical_trials({'query':'adagrasib NSCLC',...})    -> 10/27 trials
 -> #6 search_chembl({'compound_or_target':'sotorasib'})          -> CHEMBL4535757
 -> #7 search_chembl({'compound_or_target':'adagrasib'})          -> CHEMBL4594350
GUARD: coverage=100% supported=4 dropped=0
LANDSCAPE:
 - Sotorasib | Amgen      | sources=[OT:ENSG00000133703, NCT06333951, NCT05074810, ...]
 - Adagrasib | (sponsor)  | sources=[..., CHEMBL4594350]
~3.6 min wall-clock on CPU.
```

Honest notes from real local runs:

- **The reliability guard behaves identically with a local model.** In a BTK run
  where ClinicalTrials.gov data was temporarily unavailable for two drugs, the
  guard **dropped the unsupported claims and flagged those asset rows
  `unverified`** instead of letting the 7B model assert uncited facts — "no
  source, no claim" held end-to-end.
- **Small models are variable.** The same query can yield a rich landscape on one
  run and a thin/empty one on another, and a 7B model makes factual slips (e.g.
  confusing a trial *sponsor* for the asset's *originator*). The grounding
  guarantee holds regardless of model quality. For consistent, high-accuracy
  landscapes, use a frontier model (`ASSETSCOPE_LLM_BACKEND=anthropic`).
- **ClinicalTrials.gov + Python:** its WAF blocks Python's TLS fingerprint (HTTP
  403); AssetScope falls back to the system `curl` binary automatically.

## Bonus: use AssetScope via MCP

Expose AssetScope's tools to any [MCP](https://modelcontextprotocol.io) client.

```bash
pip install -e .
assetscope-mcp          # stdio transport (or: python -m assetscope.mcp_server)
```

**Claude Desktop** — edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "assetscope": {
      "command": "assetscope-mcp",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "ASSETSCOPE_USE_FAKE_EMBEDDINGS": "1",
        "ASSETSCOPE_CONTACT_EMAIL": "you@example.com"
      }
    }
  }
}
```

**Cursor** — Settings → MCP → add a server with command `assetscope-mcp`.

Restart the client; you'll get six tools:

| MCP tool | What it does |
|---|---|
| `search_clinical_trials` | Search ClinicalTrials.gov v2 |
| `search_open_targets` | Open Targets associations + tractability |
| `search_chembl` | ChEMBL mechanism / phase / IDs |
| `search_literature` | PubMed PMIDs + abstracts |
| `retrieve` | Hybrid search over the internal store |
| `build_landscape` | Run the full agent → citation-grounded landscape (needs `ANTHROPIC_API_KEY`) |

Example prompts to the MCP client:

> *“Use search_clinical_trials to find phase 3 obesity trials for orforglipron,
> then search_chembl for its mechanism.”*

> *“Call build_landscape for ‘KRAS G12C inhibitors in colorectal cancer’ and show
> me the cited table.”*
