# Measurement and acquisition contract

This technical reference records the measurement definitions checked against the final DOCX pair on October 29, 2026. It supports interpretation of existing inputs and reproduction of the retained analyses. Parameters below describe the completed study; they do not define a new intervention or authorize a new analysis run.

## Rating and exposure fields

| Parameter | Recorded definition |
| --- | --- |
| Exposure | One oral gelatin capsule; 10 microlitres of 10% w/v capsaicin solution, equivalent to 1 mg; capsaicin purity 98%, ethanol solvent 96% v/v |
| Design | Single center, single exposure; no vehicle comparison, random allocation or repeat exposure; analysis choices informed by observed outcomes |
| Eligible cohort | 215 unique exposed participants with at least one numerical rating; right-handed, age 18–40, undergraduate education or higher |
| Screening | Allergy to chili pepper, capsaicin or capsule ingredients excluded participation; gastrointestinal history and recent medication use were recorded without being exclusion criteria |
| Rating origin | Completion of the water used to swallow the capsule; first scheduled response at minute 1 |
| Rating schedule | Integer minutes 1–20; E-Prime audible prompt and 10-second keypad response window |
| Scale | Custom overall sensation score 0–10; anchors 0 = no discomfort, 1 = any discomfort, 10 = intolerable sensation; historical `VAS` names retained |
| No keypress | Recorded as zero only with the study's staff check for absent discomfort; zero and a missing response remain different analytic values |
| E | Stop after two consecutive minute-level zeros and staff confirmation of absent discomfort |
| T | Stop for intolerable sensation at score 10; nine participants |
| Post-stop observations | No numerical completion, baseline-zero insertion or filling across missing minutes |
| Safety follow-up | T participants received at least 250 mL milk and monitoring through resolution plus 30 minutes; resolution time was unmeasured; follow-up is outside the rating series |
| Food and drink | Food selection and amounts were unrecorded; the nominal cup capacity is not an independently measured administered water volume |
| Symptoms and regions | One questionnaire/oral collection after the session; multiple selections and free-description additions; 12 symptom and nine region categories |
| Symptom denominators | 209 per marginal field; 204 with both; distension and bloating use separate codes |

## Signal acquisition and alignment

| Parameter | Retained definition |
| --- | --- |
| Hb instrument | Shimadzu LABNIRS; 780/805/830 nm; 42 channels, 16 sources, 15 detectors; nominal 30-mm adjacent source-detector separation |
| Hb locations | Digitized with Polhemus and transformed to MNI coordinates through NIRS-SPM; 11 analysis groups in Table S18 |
| Hb input | Manufacturer-exported HbO/HbR on the relative concentration-change times optical-path-length scale; not absolute concentration |
| Hb sampling | 184 selected exports; interval 0.051 s (19.6078 Hz); header version 11.0; exported smoothing and baseline settings both None |
| ECG input | Three ECG100C channels: I, II and V3; gain 2000; hardware band 0.05–150 Hz; NORM waveform output |
| EGG input | Two EGG100C channels; gain 2000; 1-Hz hardware low-pass and DC high-pass setting |
| ACQ sampling and units | 140 selected recordings; original ECG/EGG sampling 2000 Hz; header units mV |
| Nominal physiological origin | Start of the selected recording or designated post-administration segment; distinct from a verified synchronized administration event |
| Block correspondence | Rating minutes 1–5, 6–10, 11–15, 16–20 map to (0,300], (300,600], (600,900], (900,1200] seconds |
| Complete support | All five numerical ratings and an available signal window; repeated-measures models require at least two eligible blocks per participant |
| Alternative timing support | Earliest longest run of at least three consecutive numerical minutes within a block; retain actual rating minutes |

## Signal processing parameters

| Domain | Parameters and eligibility |
| --- | --- |
| ECG resampling | 2000 to 250 Hz; polyphase antialias filter, Kaiser beta 8.6, linear endpoint extension |
| ECG detection | NeuroKit2 0.2.13 neurokit and kalidas2017 methods; automatic polarity handling; automatic peak-artifact correction disabled |
| ECG refinement and lead selection | Refine peaks within ±50 ms in original samples; one-to-one detector matching within 50 ms; maximize whole-record agreement, ties by lower channel index |
| RR acceptance | Consecutive primary peaks both matched; intervals 0.3–2.0 s; at least 90% detector agreement and 90% accepted-RR temporal coverage per block |
| Cardiac descriptors | HR = 60/mean accepted RR seconds; RR-RMSSD in ms from adjacent accepted RR intervals sharing their middle peak; RR-RMSSD needs at least 300 s |
| Hb masking | Derivatives in 10-s blocks with ±30-s local reference; six robust SDs, robust SD = 1.4826 × MAD; reject nonfinite/flat segments; approximately 2-s guards |
| Hb integration | Reject gaps exceeding 1.5 × median interval; time-weighted valid overlap; at least 90% temporal channel coverage in every supported block |
| Hb regional means | Same common channel set across blocks, at least ceiling(assigned channels/2), equal channel weights; center and scale by participant sample SD over eligible blocks; require nonzero SD |
| EGG masking and resampling | Eight robust SD derivative threshold and approximately 2-s guards; downsample to 10 Hz; any flagged original sample invalidates its 0.1-s bin |
| EGG spectra | Fully valid 128-s segments, 50% overlap, periodic Hann window, mean detrending, density scaling; at least two segments in each channel |
| EGG descriptors | 0.46875 cycles/min grid; maximum over 1–9 cycles/min, log mean channel band power in mV², mean channel fraction 2–4/1–9 cycles/min; trapezoidal integration of available bins |
| Extraction environment | ECG/EGG extraction: Python 3.14.6 and bioread 2025.5.2; separate from Python 3.12.13 inference and aggregate rendering |
| Timing and quality sensitivities | Frozen configurations retain offsets/drifts and stricter Hb coverage/channel thresholds; all 432 timing positions remain, including two duration-ineligible RR-RMSSD positions |

The input contracts and historical code retain their existing identifiers. This documentation update does not change processing code, QC thresholds, scientific gates or original inputs. Use [physiological inference](physiology_20261017.md) for controlled execution, [field definitions](field_contract.md) for coding, and [reproducibility](reproducibility.md) for public aggregate exports. Recording selection and signal screening precede model eligibility; their target-specific counts are retained in Table S19.
