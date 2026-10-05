# History cleanup and publication

The latest reviewed public tree was published as a new parentless snapshot on October 5, 2026, following the owner's request to remove history associated with older manuscript and supplementary documents. Earlier Git histories, bundles, and verification records are retained in a restricted local archive outside this repository. Identifiers that locate retained sensitive objects are kept in that private archive and are not repeated here.

The snapshot contains the current English README, formatted Python/R code, synthetic tests, method configurations, and reviewed aggregate outputs. Historical manuscript/supplement stubs, narrative reports, and submission-planning files are excluded from its reachable history. The research inputs, analytical code, method parameters, numerical tables, and figure bytes are unchanged by this history operation.

## Verification and publication

Before publication, run the current-tree and complete-history checks:

```sh
python3 scripts/verify_repository_structure.py
python3 scripts/verify_public_release.py
python3 scripts/verify_public_history.py
```

The history check rejects participant artifacts, invalid inventory hashes, non-regular entries, shallow or redirected history, changing refs, and unreachable stored objects. It does not certify scientific validity or removal from external copies.

Replace remote main only against its independently observed previous value, using an explicit force-with-lease. Do not use an unconditional force or mirror push. Verify remote refs and a fresh full clone after replacement. Restore normal fetching only after the remote head is confirmed. Existing clones must be replaced or cleaned before further contributions; merging a former clone can reconnect removed history.

The dated verification snapshots in this repository describe their original checks. The [publication status](publication_status.json) records the current operation's confirmed phase. Detailed commit identifiers and publication evidence remain in the private archive.

The replacement was confirmed at remote main, and a fresh full GitHub clone passed all three checks. It contained one root commit and excluded the former publication history and both complete-writing blobs. The subsequent receipt update contains only verification metadata.

## Remaining host-side cleanup

Full older manuscript and supplementary documents were absent from advertised GitHub branches/tags but still retrievable as retained objects. Removing commits from branch history does not delete these server-side objects. A successful push and clean clone are separate from server-side erasure.

[GitHub's sensitive-data removal documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository#fully-removing-the-data-from-github) describes requesting server-side garbage collection and cached-view removal through GitHub Support. GitHub determines eligibility for that process. A support request and object evidence are prepared outside Git; submission and completion must be recorded only after they are confirmed. No claim of complete historical erasure is made while host retention remains unresolved.
