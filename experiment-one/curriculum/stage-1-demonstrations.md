# ΛLingua v0 — Demonstrations

## Demonstration 1

Source:
LOG101 shows that the nightly backup job failed. Whether the storage quota was exceeded is unknown.

Terms: BACKUP_JOB_FAILED, STORAGE_QUOTA_EXCEEDED

ΛLingua v0:

    φ:BACKUP_JOB_FAILED ∵ ε:LOG101
    ?:STORAGE_QUOTA_EXCEEDED

Why:
- φ: the source states that the backup job failed.
- ε: LOG101 is an evidence item.
- ∵: LOG101 is the stated evidence for the failure.
- ?: the source says it is unknown whether the quota was exceeded; it is neither asserted nor proposed.

## Demonstration 2

Source:
Page loads were slow; no evidence item is cited for this. A misconfigured CDN cache has been put forward as a cause. TRACE102, a request trace, is on file; no finding is drawn from it.

Terms: CDN_CACHE_MISCONFIGURED, SLOW_PAGE_LOADS

ΛLingua v0:

    φ:SLOW_PAGE_LOADS
    ε:TRACE102
    ĥ:CDN_CACHE_MISCONFIGURED

Why:
- φ: the source states that page loads were slow; no evidence is cited, so there is no ∵.
- ε: TRACE102 is an evidence item, but it supports no statement, so it stands alone.
- ĥ: the CDN cache is only proposed as a cause; it is not asserted.

## Demonstration 3

Source:
E103 shows that the TLS certificate expired. E104 shows that the renewal job did not run. Whether the renewal job was disabled is unknown. Clock drift on the renewal host has been put forward as a cause.

Terms: RENEWAL_HOST_CLOCK_DRIFT, RENEWAL_JOB_DISABLED, RENEWAL_JOB_NOT_RUN, TLS_CERT_EXPIRED

ΛLingua v0:

    φ:TLS_CERT_EXPIRED ∵ ε:E103
    φ:RENEWAL_JOB_NOT_RUN ∵ ε:E104
    ?:RENEWAL_JOB_DISABLED
    ĥ:RENEWAL_HOST_CLOCK_DRIFT

Why:
- φ: the source states both events.
- ε and ∵: each assertion keeps its own evidence item; E103 and E104 are not swapped or merged.
- ?: whether the job was disabled is unknown, even though it would be a plausible explanation.
- ĥ: clock drift is only proposed; it stays a hypothesis however plausible it seems.
