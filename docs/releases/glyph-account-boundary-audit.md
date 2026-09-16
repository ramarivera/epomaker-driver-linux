# Glyph local and account-bound workflows

Static comparison of the pinned Windows and macOS main bundles. No login, cloud
request, upload or device operation was performed. This narrows the unresolved
G14.1 applicability question; it does not exclude cloud features from parity.

| Source | SHA-256 |
| --- | --- |
| Windows `index.feaf50e4.js` | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` |
| macOS `index.5af2e057.js` | `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` |

The following zero-based UTF-8 byte offsets were checked directly against both
files, rather than inferred from character positions:

| Handler | Windows | macOS | Observed boundary |
| --- | ---: | ---: | --- |
| `handleShareMacro` | 1752032 | 1760844 | Rejects undefined `currentUser` before sharing |
| `handleShareConfig` | 1752686 | 1761498 | Same account guard before selecting the current device/configuration |
| `getIOTSwitch=async` | 1719943 | 1728755 | Reads a local service/UI setting; this is separate from the account guard |
| `userLogin` | 1259234 | 1264675 | Calls login with email/password, then obtains a web session |

Local named key configurations and macros already have independent Linux storage:
`src/epomaker_driver/config_library.py` and `src/epomaker_driver/macro_library.py`.
These do not implement the sharing handlers. The macOS comparison confirms the
same explicit login boundary as Windows, not a platform-specific exclusion.

Remaining evidence needed: trace every rendered cloud/community entry point for
Glyph, its complete transfer envelope and service authorization requirements.
The presence of an account-gated shared handler alone does not prove every
community endpoint's authorization policy, nor that cloud access is necessary
for ordinary keyboard configuration. No account credentials are required for
continuing the local binary audit.
