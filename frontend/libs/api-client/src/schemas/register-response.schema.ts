import { z } from 'zod';
import { UserSchema } from './user.schema';

export const RegisterResponseSchema = z.object({
  user: UserSchema,
});
