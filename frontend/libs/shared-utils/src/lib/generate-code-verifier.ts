import { base64UrlEncode } from './base64-url-encode';

/**
 * Generate a random code_verifier for PKCE (43-128 chars, unreserved characters).
 */
export function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return base64UrlEncode(array);
}
