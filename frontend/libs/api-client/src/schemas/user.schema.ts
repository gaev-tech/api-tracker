import { z } from 'zod';

export const UserSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  email: z.string().email(),
  theme: z.enum(['light', 'dark']),
  language: z.string(),
  is_active: z.boolean(),
  email_verified_at: z.string().nullable().optional(),
  created_at: z.string(),
});
