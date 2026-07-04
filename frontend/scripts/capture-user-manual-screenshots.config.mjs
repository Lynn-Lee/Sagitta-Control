export function validateScreenshotCaptureConfig({ username, password, smokeOnly }) {
  if (!smokeOnly && (!username || !password)) {
    throw new Error(
      'E2E_USERNAME/E2E_PASSWORD are required before overwriting authenticated user manual screenshots. ' +
        'Use npm run e2e:smoke for redirect-only checks without credentials.',
    )
  }
}
