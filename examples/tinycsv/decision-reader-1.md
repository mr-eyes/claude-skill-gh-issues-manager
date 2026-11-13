### Decision: 2026-03-04 15:55 PST - strict quoting is the default

**Decision:** Strict quoting is the default mode of the reader.

**Decided by:** Sam Rivera, 2026-03-04 15:55 PST

**Exact words:**

> Make strict the default. A file with a stray quote should fail, not load wrong rows. People who want the sloppy mode can ask for it.

**Where recorded:** Chat with the Claude session on 2026-03-04.

**Effect:** `strict=True` becomes the default argument, and the release-notes text on this issue lists it under Changed. The conformance numbers on this issue are for strict quoting.

**Next step:** Document the lenient mode in the README, owner Claude session
