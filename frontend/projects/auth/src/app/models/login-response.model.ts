import { z } from 'zod';
import { LoginResponseSchema } from '@libs/api-client';

export type LoginResponse = z.infer<typeof LoginResponseSchema>;
