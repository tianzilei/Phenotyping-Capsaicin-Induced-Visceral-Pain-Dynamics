# Restricted data handling

Individual ratings, symptom records, source signals, identity mappings and free text belong in controlled storage outside the publication tree. Exact trajectories and demographic combinations can remain identifying after direct identifiers are removed.

The export utility creates random identifiers, keeps linked records consistent within one export, shuffles rows and refuses an existing destination. Explicit field selection excludes free text and source links. Keep its identity mapping separately from any sharing copy. Pseudonymized records are restricted records.

The exporter compares source bytes before and after copying. On POSIX systems it requests directory mode 0700 and file mode 0600; on Windows, access control must be set using the storage location's ACLs. Numerical content, categorical markers and original missing tokens are preserved.

Current-tree checks reject participant-shaped columns in non-synthetic tables, raw-signal extensions, local credentials and personal source paths. A passing scan is not a certification that sharing is ethically or legally authorized.
