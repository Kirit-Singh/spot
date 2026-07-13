# The method the historical v1 release was BOUND to (as of `e410d72`)

The release beside this directory (`fed2a8347d155a23`) binds `method_file_sha256` over the seven
v1 method files **as they were at `e410d72`**. Verifying a historical artifact means recomputing
it from *its own* bound inputs — not from today's.

They are not identical to `04_PKPD/method/` any more, and that is correct, not drift:

**W8's `9c857fb` corrected `sources.json`.** It used to say DailyMed was
`"Public domain (NLM DailyMed)"`. That was an overclaim — DailyMed publishes no blanket licence
and some SPL content carries third-party copyright (source audit §4.6). The entry now records
`no_blanket_license_verified`, the terms URL, and the in-use-vs-approved caveat.

That correction MUST move the method hash — a method binding that did not move when the method
changed would be worthless. So a release emitted before the correction can no longer be
reproduced from today's method, and pretending otherwise would mean either reverting a true
statement about licensing or forging a hash. Neither is acceptable.

What the freeze test actually claims is about the **contract**: today's v2-aware verifier can
still fully reconstruct a v1 release. It supplies the method that release was bound to, which is
what verifying a historical artifact requires. It does not claim the method is immutable — the
method is *supposed* to be correctable, and this is what a correction looks like.
