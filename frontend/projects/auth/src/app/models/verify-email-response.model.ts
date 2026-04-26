import { z } from 'zod';
import { VerifyEmailResponseSchema } from '@libs/api-client';

export type VerifyEmailResponse = z.infer<typeof VerifyEmailResponseSchema>;
