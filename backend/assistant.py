"""Grounded project Q&A. A deterministic local assistant, not a general LLM."""
import re
from backend.dashboard import snapshot


def answer(message,language='en'):
    q=message.lower().strip()
    hi=language=='hi'
    data=snapshot()
    cohort,pipeline,model=data['cohort'],data['pipeline'],data['model']
    def response(en,hin,source):
        return {'answer':hin if hi else en,'source':source,'engine':'local-project-guide'}
    if any(w in q for w in ['accuracy','99','score','सटीक','एक्यूरेसी','स्कोर']):
        acc=model['metrics'].get('accuracy')
        ba=model['metrics'].get('balanced_accuracy')
        if acc is None or ba is None:
            return response('Saved model scores are unavailable.','सहेजे गए मॉडल स्कोर उपलब्ध नहीं हैं।','Saved model metadata')
        return response(f'The V2 development selection accuracy is {acc*100:.2f}% and balanced accuracy is {ba*100:.2f}%. These were used for model selection, so they are not independent test accuracy. The sequence expansion has not produced a new accuracy result, and 99% has not been established. A fresh independent evaluation is still required.',
            f'V2 की development selection accuracy {acc*100:.2f}% और balanced accuracy {ba*100:.2f}% है। ये मॉडल चुनने के स्कोर हैं, स्वतंत्र test accuracy नहीं। नए sequence features की accuracy अभी मापी नहीं गई है और 99% साबित नहीं हुआ है। नया स्वतंत्र मूल्यांकन अभी ज़रूरी है।','Saved V2 development selection')
    if any(w in q for w in ['status','progress','complete','running','kitna','hua','प्रगति','पूरा','स्थिति','कितना','चालू']):
        c,t=pipeline['completed'],pipeline['total']
        return response(f'The assembly stage is {pipeline["status"]}: {c} of {t} assemblies are annotated. {cohort["read_completed"]} of {cohort["read_sources"]} read-derived genomes are processed. There are {len(pipeline["failures"])} recorded assembly failures. Species QC and a full cohort audit follow annotation; retraining comes after the remaining read genomes and QC.',
            f'Assembly चरण की स्थिति {pipeline["status"]} है: {t} में से {c} assemblies annotated हैं। Read samples में {cohort["read_sources"]} में से {cohort["read_completed"]} process हो चुके हैं। दर्ज assembly failures: {len(pipeline["failures"])}। Annotation के बाद species QC और audit होंगे; बाकी read genomes और QC के बाद retraining होगी।','Live processing manifests')
    if any(w in q for w in ['scatter','heatmap','chart','graph','plot','ग्राफ','चार्ट','हीटमैप']):
        return response('Explore shows the original exploratory cohort: gene count versus anomaly score, cluster distribution, and gene prevalence by cluster. The model bar chart shows development-fold recall. The confusion heatmap belongs to the historical V1 test. These views describe different cohorts; the labels under each chart identify their source.',
            'Explore में पुराने exploratory cohort का gene count बनाम anomaly score, cluster distribution और gene prevalence दिखता है। मॉडल bar chart development folds का recall दिखाता है। Confusion heatmap पुराने V1 test का है। हर chart के नीचे उसका data source दिया गया है।','Visualization guide')
    if any(w in q for w in ['data','cohort','samples','dataset','डेटा','नमूने','सैंपल']):
        return response(f'The supervised development cohort contains {cohort["total"]} samples from {cohort["projects"]} BioProjects: {cohort["susceptible"]} susceptible and {cohort["resistant"]} resistant. The target is ceftazidime under CLSI labels. {cohort["assembly_sources"]} have assembly sources and {cohort["read_sources"]} have paired-read sources.',
            f'Supervised development cohort में {cohort["projects"]} BioProjects के {cohort["total"]} samples हैं: {cohort["susceptible"]} susceptible और {cohort["resistant"]} resistant। लक्ष्य ceftazidime है और labels CLSI के हैं। {cohort["assembly_sources"]} assembly sources तथा {cohort["read_sources"]} paired-read sources हैं।','Frozen development cohort')
    if any(w in q for w in ['quality','contamin','qc','क्वालिटी','गुणवत्ता']):
        return response('QC combines verified source checksums, species screening, assembly metrics, and read-to-assembly mapping where reads are available. These checks do not prove absence of contamination. The uniform-Q30 pilot sample is retained with a source-quality flag. Comprehensive contamination assessment is still pending.',
            'QC में source checksum, species screen, assembly metrics और उपलब्ध reads की mapping शामिल है। इनसे contamination का न होना साबित नहीं होता। Uniform-Q30 वाला pilot sample quality flag के साथ रखा गया है। व्यापक contamination assessment अभी बाकी है।','QC processing plan')
    if any(w in q for w in ['workflow','project','explain','how','pipeline','kaise','समझा','प्रोजेक्ट','कैसे','कार्य']):
        return response('ResistMap links bacterial genomes to laboratory resistance labels, verifies and processes sequence data, extracts genomic features, and compares models with BioProject-separated validation. Exploratory anomaly scores prioritize unusual samples for review. The workflow ends with fresh independent evaluation and a research dashboard; it does not diagnose or choose treatment.',
            'ResistMap bacterial genomes को laboratory resistance labels से जोड़ता है। Sequence data की जाँच और processing के बाद genomic features बनते हैं। मॉडल को BioProject-अलग validation से compare किया जाता है। Anomaly scores असामान्य samples की समीक्षा में मदद करते हैं। अंत में स्वतंत्र मूल्यांकन और research dashboard आते हैं; यह diagnosis या treatment चुनने का tool नहीं है।','Project workflow')
    if any(w in q for w in ['predict','upload','input','अपलोड','भविष्यवाणी']):
        return response('Choose Add input to enter samples and AMR calls manually, paste a CSV/TSV table, or upload a file with BioSample and AMR genotypes. It previews COMPLETE and POINT entries without storing the uploaded file. The new sequence model is not connected for inference yet, so this screen does not generate predictions.',
            'Add input से sample और AMR calls खुद लिखें, CSV/TSV table paste करें या BioSample और AMR genotypes वाली file अपलोड करें। File को save किए बिना COMPLETE और POINT entries का preview मिलता है। नया sequence model अभी inference से connected नहीं है, इसलिए इस screen से predictions नहीं बनतीं।','Input workspace contract')
    return response('I can help with this workspace: processing progress, model accuracy, the dataset, QC, charts, or the project workflow. Try “What is the current progress?” or “Explain the accuracy scores.”',
        'मैं इस workspace की processing progress, model accuracy, dataset, QC, charts और workflow समझा सकता हूँ। पूछें: “अभी कितना काम पूरा हुआ?” या “Accuracy scores समझाओ।”','Project guide • local answers')
