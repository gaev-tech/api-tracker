import { z } from 'zod';

export const TokenPairSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
});
