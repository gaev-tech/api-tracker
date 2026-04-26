import { z } from 'zod';
import { UserSchema } from './user.schema';

export const VerifyEmailResponseSchema = z.object({
  user: UserSchema,
});
