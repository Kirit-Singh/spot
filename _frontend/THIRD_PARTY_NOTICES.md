# Third-party notices

The spot downstream frontend (`_frontend`) bundles the following third-party packages. Their exact
resolved versions are pinned in `package-lock.json`.

## @noble/hashes (^2.2.0) — MIT

Used for a deterministic SHA-256 (`src/stage1/canonical.ts`) so content-address verification works
in an insecure browser context where WebCrypto (`crypto.subtle`) is unavailable (the `:8347`
distribution is served over plain HTTP on a non-localhost origin). Zero runtime dependencies.

    MIT License — Copyright (c) 2022 Paul Miller (https://paulmillr.com)

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software
    and associated documentation files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or
    substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
    BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## react / react-dom (^19.2.7) — MIT, © Meta Platforms, Inc.

Standard MIT terms apply (same permission/warranty text as above).

_This file is a source-tree license record. It is not part of the served `:8347` distribution; the
served release is inventoried and hashed in `release_manifest.json`._
