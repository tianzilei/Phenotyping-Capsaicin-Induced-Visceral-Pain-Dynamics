# Input field contract

Wide rating tables require a unique participant key and columns for the expected actual minutes. Numerical scores must fall within the configured scale. The parser preserves numerical values, missing entries and categorical stopping markers. Numeric observations after a stopping marker, mixed stopping markers and duplicate participant keys are rejected.

Zero is a numerical observation. A missing cell is not zero. Adjacent-change calculations require observed consecutive minutes; incomplete intervals are not connected by interpolation. The input format does not supply a baseline observation.

Registry-based source selection uses explicit paths, acquisition dates and unique ownership. Tied dates for different paths remain ambiguous. A registry documents a selection decision; it does not establish signal quality or biological validity.

Reference-admission metadata identify the source record, reviewer, independent-human attestation, adjudication and annotation version. Required metadata are a contract, not proof that an annotation is correct.

Blank schemas and synthetic fixtures describe interfaces. They do not grant scientific readiness or permission to process real records.
