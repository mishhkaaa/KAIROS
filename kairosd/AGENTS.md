# kairosd/ — owner P1. Composition root: the ONLY code allowed to import every split's package.
- Add a component = one row in `REGISTRY` (component, bundle attribute, fake builder, "module:function" of the real factory).
- Keep the fallback behaviour (real factory raising NotImplementedError → fake + warning).
