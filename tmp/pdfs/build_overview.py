from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from pypdf import PdfReader

ROOT = Path('D:/ResistMap-AI')
OUT = ROOT / 'output/pdf/ResistMap_AI_Project_Overview_English.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyCustom', fontName='Helvetica', fontSize=10, leading=14, spaceAfter=9, textColor=colors.HexColor('#243447')))
styles.add(ParagraphStyle(name='SmallCustom', fontName='Helvetica', fontSize=8, leading=11, spaceAfter=6))
styles['Title'].textColor=colors.HexColor('#12344A')
styles['Heading1'].textColor=colors.HexColor('#087F8C')
styles['Heading1'].fontSize=19
styles['Heading2'].fontSize=12
styles['Heading2'].textColor=colors.HexColor('#12344A')
story=[]
def p(t, style='BodyCustom'): story.append(Paragraph(t, styles[style]))
def h(t): p(t,'Heading2')
def page(title):
    if story: story.append(PageBreak())
    p(title,'Heading1'); story.append(Spacer(1,9))
def table(headers, rows, widths):
    data=[[Paragraph(str(v),styles['SmallCustom']) for v in r] for r in [headers]+rows]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCEFF0')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,0),1,colors.HexColor('#087F8C')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7FA')])]))
    story.append(t);story.append(Spacer(1,10))
def source(t): p('Repository evidence: '+t,'SmallCustom')

page('ResistMap AI | Project Overview')
p('Datasets, preprocessing, algorithms, results and remaining work','Title')
p('Status review: 16 November 2026 | English edition','SmallCustom')
h('Purpose and scope')
p('ResistMap AI is a genomic antimicrobial resistance (AMR) research platform. It uses bacterial gene and mutation profiles to study resistance patterns, predict resistant or susceptible outcomes for selected antibiotics, group similar profiles, and identify unusual profiles for review.')
p('Four organisms are represented: <b>Klebsiella pneumoniae, Escherichia coli, Acinetobacter baumannii</b> and <b>Mycobacterium tuberculosis</b>. The pneumonia-related organism implemented here is K. pneumoniae. No separate Streptococcus pneumoniae model or chest X-ray pneumonia classifier was found in the reviewed repository.')
table(['Organism','Current milestone','User-facing prediction'],[
['K. pneumoniae','V1/V2 classifiers trained; sequence expansion under QC','V2 ceftazidime inference integrated'],
['E. coli','21 drug-standard baseline models trained; large-scale exploratory analyses','Development summaries only'],
['A. baumannii','9 drug-standard baseline models trained; large-scale exploratory analyses','Development summaries only'],
['M. tuberculosis','Mutation matrix completed; 28 drugs represented in labels','Training and inference pending']], [100,255,155])
h('How the project works')
p('Dataset acquisition → label and identifier cleaning → genomic feature encoding → group-aware partitioning → model training or exploratory analysis → evaluation → dashboard reporting. Raw sequence processing is currently handled by command-line scripts rather than the web upload interface.')
h('How to interpret this report')
p('This is a review of saved code and artifacts, not a new training or validation run. Dataset counts refer to different processing stages and must not be added together. Laboratory susceptibility measurement rows may contain several drugs for the same sample. Internal development scores do not establish independent or clinical performance.')
source('README.md; FRONTEND.md; backend/prediction.py; data/processed/multispecies/*/encoded/supervised_models/report.json')

page('1 | Available datasets and cohort sizes')
table(['Organism','Raw data available','Processed data'],[
['K. pneumoniae','Isolate metadata, AMR profiles, AST table, assemblies and reads','3,000-isolate exploratory cohort; 445-sample supervised development cohort'],
['E. coli','572,745 isolate rows; 183,438 AST measurement rows','523,625 descriptive profiles x 8,103 features; supervised subset: 3,694 x 512'],
['A. baumannii','66,032 isolate rows; 22,896 AST measurement rows','64,033 descriptive profiles x 1,192 features; supervised subset: 798 x 191'],
['M. tuberculosis','660,961 initial measurement rows; genome, sequencing, mutation and variant tables','51,012 samples x 1,850,698 features; 404,897 matched sample-drug labels across 28 drugs']], [92,200,218])
h('Primary files')
p('<b>Klebsiella:</b> data/raw/isolates.tsv, isolates_with_metadata.tsv and klebsiella_ast.tsv; processed features in data/processed/klebsiella_amr_features.csv.')
p('<b>E. coli:</b> data/multispecies/escherichia_coli/ecoli_isolates.tsv and ecoli_ast.tsv. <b>A. baumannii:</b> the corresponding abaumannii_isolates.tsv and abaumannii_ast.tsv files in its species directory.')
p('<b>TB:</b> DST_MEASUREMENTS.parquet, DST_SAMPLES.parquet, GENOMES.parquet, WGS_SAMPLES.parquet, MUTATIONS.parquet, VARIANTS.parquet, DRUG_CODES.csv.gz and DATA_SCHEMA.pdf in data/multispecies/tuberculosis/.')
h('Why the supervised cohorts are smaller')
p('The large profile matrices support descriptive analysis even without usable phenotype labels. Supervised subsets additionally require compatible resistance labels, genomic features, and the grouping information used for development partitions. They are subsets of existing data, not additional independent cohorts.')
h('Documentation needs reconciliation')
p('The older multispecies README and manifest still describe E. coli and A. baumannii as pending. Later encoded datasets, saved model files and training reports show that baseline training has occurred. Stage-specific reports should take precedence over these older summaries.')
source('data/processed/multispecies/*/qc_report.json; */unsupervised_profiles/report.json; */encoded/report.json; tuberculosis/features/report.json')

page('2 | Cleaning and preprocessing: E. coli and A. baumannii')
table(['Cleaning stage','E. coli','A. baumannii'],[
['Initial AST rows','183,438','22,896'],
['Exact duplicate AST rows','0','1,394'],
['Non-binary or missing phenotype exclusions','39,382','1,729'],
['Species-mismatch AST exclusions','12,623','1,006'],
['Conflicting sample-drug label exclusions','15','282'],
['Initial cleaned candidate label rows','131,418','18,485'],
['Unique samples in candidate label set','8,621','1,141'],
['Isolate-table species mismatch exclusions','40,917','1,977'],
['Missing AMR-profile exclusions','7,938','No separate category reported'],
['Ambiguous BioSample row exclusions','265','22'],
['Final descriptive profiles','523,625','64,033']], [260,125,125])
h('Encoding and partitioning')
p('Gene/mutation calls and detection status are preserved as separate sparse binary tokens. Blank profiles are treated as unknown rather than wild type. An absent token means not reported in the annotation, not confirmed biological absence. Testing standards are retained separately; unknown standards are routed for review.')
table(['Species','Train','Validation','Internal test','Features'],[
['E. coli','2,934','304','456','512'],['A. baumannii','482','255','61','191']], [150,90,90,90,90])
p('The saved split checks report separation of BioSamples, known clusters, shared assemblies and identical profiles. This does not certify complete phylogenetic independence. Cluster-missing records were excluded from these supervised subsets. Class balancing uses training-time model weights; validation and test data were not resampled.')
source('data/processed/multispecies/escherichia_coli/ and acinetobacter_baumannii/: qc_report.json, unsupervised_profiles/report.json, encoded/report.json; tools/prepare_multispecies_cohorts.py')

page('3 | Cleaning and preprocessing: TB and Klebsiella')
h('TB: phenotype cleaning and quality filters')
p('The initial 660,961 measurement rows included 462 exact duplicates. Cleaning excluded 43,524 non-binary or missing phenotype rows and 8,118 conflicting sample-drug label rows, leaving 608,857 candidate rows across 65,568 samples before subsequent genomic QC and matching.')
p('The cohort preparation code applies high/medium phenotype quality, exact M. tuberculosis species, complete sequencing status, coverage of at least 95%, depth of at least 20, a single lineage, available mutation data, and a valid sample accession. Discordant accession-drug labels are excluded.')
h('TB: completed feature construction')
p('The saved matrix contains <b>51,012 samples, 1,850,698 mutation features and 74,783,493 nonzero entries</b>. It matches 404,897 binary label rows across 28 drugs. A total of 38 mapping rows affecting 19 ambiguous sample accessions were quarantined; another 22 samples without valid mutation features were excluded.')
p('Reload checks passed for dimensions, binary values, nonempty rows, unique mappings, row indexing, label uniqueness and feature-name alignment. The current vocabulary describes the retained full cohort. Predictive work still requires grouped partitions and training-only feature selection or vocabulary construction. No TB accuracy has been established.')
h('Klebsiella: existing models and sequence expansion')
p('Ceftazidime prediction uses binary gene and point-mutation calls. The sequence pipeline includes fastp cleaning, SKESA assembly, AMRFinderPlus annotation, and species/mapping-related QC using Kleborate, minimap2 and samtools. Processing is checkpointed so completed steps can be preserved.')
p('The latest saved read-job status reports <b>130 of 130 requested samples completed preliminary read processing</b>, with no listed failures. It also explicitly states contamination screening is pending and no expanded-feature model or accuracy measurement was produced by that job.')
h('Important status inconsistency')
p('An older reconciled inventory reports 341 of 445 samples available and 104 missing, while the later read-job status reports all 130 requested read samples completed. Reconciliation must be refreshed before stating the final combined feature count. Completion of preliminary processing does not establish biological QC clearance.')
source('reports/tb_feature_completion.md; tools/prepare_multispecies_cohorts.py; results/ceftazidime_sequence_scaleup/reads/read_job_status.json; reconciled/inventory.json')

page('4 | Algorithms and analysis performed')
table(['Method','Use and implementation status'],[
['Random Forest','Klebsiella V1/V2 prediction. Selected V2: 600 trees, balanced class weights, minimum leaf size 4; resistance threshold 0.40.'],
['Logistic Regression','21 E. coli and 9 A. baumannii drug-standard baselines trained using balanced class weights and liblinear; also a Klebsiella comparison candidate.'],
['Extra Trees / Histogram Gradient Boosting','Klebsiella candidate-model comparisons; neither is the selected V2 model.'],
['K-Means / MiniBatchKMeans','Clustering of AMR profiles, including scalable sparse and reduced-representation comparisons.'],
['Hierarchical clustering / PCA','Initial exploratory notebook experiments.'],
['Truncated SVD','32-component descriptive representations for E. coli and A. baumannii sparse matrices.'],
['L2 normalization','Compared with unnormalized profile representations to assess clustering behavior.'],
['HDBSCAN','Exploratory density clustering on 8,000 unique E. coli training profiles; not a production classifier.'],
['Isolation Forest','Anomaly scoring with seed-stability and group-bootstrap resampling audits.'],
['Group-aware evaluation','Known-relatedness grouping, training-only transformations in later evaluation, and overlap checks.'],
['UMAP','Optional support; not counted here as a completed primary result.']], [155,355])
h('What the exploratory results mean')
p('Initial SVD-space clustering selected 2 groups for E. coli and 8 for A. baumannii. A normalized E. coli experiment selected 16 groups. These are alternative exploratory results, not validated resistance classes. Later grouped and direct-sparse comparisons tested other cluster counts without automatically promoting a final model.')
p('Anomaly ranking and cluster stability were tested across seeds and resampled groups. Unusual profiles still need biological review. Clusters do not establish transmission chains, and anomaly flags do not prove novel resistance or an outbreak.')
source('tools/train_multispecies_supervised.py; results/ceftazidime_v2_20261001T202849_616568Z/metadata.json; data/processed/multispecies/*/unsupervised_profiles/ analysis reports')

page('5 | Model results and application status')
table(['Model','Accuracy','Balanced accuracy','Evaluation context'],[
['Klebsiella V1','87.72%','89.34%','Historical 114-sample test'],
['Klebsiella V2','90.37%','83.66%','Mean development-CV selection scores'],
['E. coli baseline','96.04%','94.03%','Macro average across 21 internal-test tasks'],
['A. baumannii baseline','74.30%','69.22%','Macro average across 9 internal-test tasks'],
['TB','Not available','Not available','Model training pending']], [125,75,95,215])
p('These scores are not directly comparable because cohorts, endpoints and evaluation methods differ. The E. coli and A. baumannii values are averages across tasks, not guarantees for every antibiotic. The historical Klebsiella test informed subsequent development and cannot serve as an untouched independent V2 test.')
h('Antibiotic coverage')
p('<b>E. coli:</b> amoxicillin-clavulanic acid, ampicillin, aztreonam, cefazolin, cefepime, cefoxitin, ceftazidime, ceftiofur, ceftriaxone, chloramphenicol, ciprofloxacin, gentamicin, levofloxacin, nalidixic acid, piperacillin-tazobactam, sulfisoxazole, tetracycline, tobramycin, trimethoprim and trimethoprim-sulfamethoxazole. Cefoxitin appears under two testing standards, giving 21 tasks across 20 drugs.')
p('<b>A. baumannii:</b> amikacin, ampicillin-sulbactam, ceftazidime, imipenem, levofloxacin, meropenem, tetracycline, tobramycin and trimethoprim-sulfamethoxazole. <b>Klebsiella integrated endpoint:</b> ceftazidime.')
h('Application features implemented')
p('The local dashboard includes authentication, English/Hindi language selection, themes, sample browsing and filters, charts, exports, manual input, CSV/TSV paste/upload, a project-data-based chatbot, and an explanatory video. A research-paper draft and PDF are also saved in the repository.')
p('Prediction is currently restricted to confirmed complete K. pneumoniae annotated profiles. The response includes the predicted label, resistance score, threshold and unseen features. Samples without recognized features receive no prediction. Scores are not calibrated confidence, and this guard is not a validated out-of-distribution detector.')
p('Local speech transcription is implemented, but the latest TB completion report records two speech-test failures caused by missing dependencies and a missing audio fixture in the selected environment. Current voice functionality requires re-verification.')
source('results/ceftazidime_clsi_test_scores_v1.csv; reports/ieee_paper/README.md; */encoded/supervised_models/report.json and metrics.csv; FRONTEND.md; backend/prediction.py')

page('6 | External data and remaining work')
table(['External candidate','Available / screened','Conclusion'],[
['E. coli: PRJEB115520','99 sample records','All previously seen; rejected as fresh external test'],
['A. baumannii: PRJNA1286014','151 assembly/sample records','All previously seen'],
['A. baumannii: PRJNA573295','125 sample records','All previously seen'],
['Liverpool E. coli','736 metadata records; 762 genome files','Accession crosswalk and independence unresolved']], [150,145,215])
p('The Liverpool genome scan found 762 unique exact contig sets, but exact deduplication does not establish independence from development data or exclude related lineages. Metadata and genome counts should not yet be treated as a verified one-to-one matched cohort. Annotation-version differences also require review.')
h('Priority roadmap')
for title, body in [
('1. Reconcile status and inventories','Refresh outdated manifests and merge completed sequence checkpoints into a current feature inventory.'),
('2. Finalize Klebsiella sequence QC','Complete contamination screening, biological review and inclusion decisions, then train and evaluate an expanded-feature model.'),
('3. Train TB baselines','Create group-aware partitions, derive training-only features and train eligible per-drug models with adequate class support.'),
('4. Improve multispecies baselines','Review per-drug errors and weak tasks, particularly the smaller A. baumannii test cohort and uneven performance.'),
('5. Establish independent validation','Acquire separately sourced, overlap-checked cohorts; verify provenance and freeze preprocessing, models and endpoints before evaluation.'),
('6. Validate biological interpretations','Review anomalies and cluster associations against an explicit independent reference standard.'),
('7. Extend the application','Integrate species/drug-specific inference, controlled raw-genome processing, and re-verify speech functionality.'),
('8. Add uncertainty and deployment readiness','Evaluate calibration and genomic familiarity; conformal prediction and outbreak alerts remain proposed. Review deployment and authentication before public use.')]:
    p('<b>'+title+'.</b> '+body)
source('data/external/multispecies_candidate_screen/screen_report.json and liverpool_genome_readiness.json; reports/multispecies_validation_readiness/validation_protocol.md')
p('<b>Current conclusion:</b> Cleaning and preprocessing have been performed for all four organisms. Supervised models exist for three; TB feature construction is complete. User-facing prediction is integrated for Klebsiella, while fresh independent validation remains the major research milestone.','SmallCustom')

def footer(canvas,doc):
    canvas.setStrokeColor(colors.HexColor('#D7E2EA'));canvas.line(42,39,553,39)
    canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#536779'))
    canvas.drawString(42,25,'ResistMap AI | Repository status review | 16 November 2026')
    canvas.drawRightString(553,25,str(doc.page))
doc=SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=52,title='ResistMap AI - Project Overview',author='ResistMap AI')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
reader=PdfReader(str(OUT))
print('Created:',OUT,'Pages:',len(reader.pages))
for i,page_ in enumerate(reader.pages):
    text=page_.extract_text()
    print(i+1,len(text),text[:85].replace('\n',' '))
