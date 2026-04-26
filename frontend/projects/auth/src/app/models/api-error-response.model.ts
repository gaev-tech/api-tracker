import { z } from 'zod';
import { ErrorResponseSchema } from '@libs/api-client';

export type ApiErrorResponse = z.infer<typeof ErrorResponseSchema>;
