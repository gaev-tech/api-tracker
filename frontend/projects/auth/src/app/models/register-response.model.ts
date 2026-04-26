import { z } from 'zod';
import { RegisterResponseSchema } from '@libs/api-client';

export type RegisterResponse = z.infer<typeof RegisterResponseSchema>;
