The seccomp profile is vendored unchanged from the official Playwright v1.64.1
Docker sources: https://github.com/microsoft/playwright/blob/v1.64.1/utils/docker/seccomp_profile.json

Playwright is distributed under Apache-2.0:
https://github.com/microsoft/playwright/blob/v1.64.1/LICENSE

The profile retains an allowlist with a default errno action and adds the user
namespace calls needed by Chromium sandboxing. Never substitute an unconfined
seccomp profile or disable Chromium sandboxing to make deployment pass.
