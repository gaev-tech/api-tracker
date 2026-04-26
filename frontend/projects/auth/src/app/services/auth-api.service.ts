import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { LoginRequest } from '../models/login-request.model';
import { LoginResponse } from '../models/login-response.model';
import { RegisterRequest } from '../models/register-request.model';
import { RegisterResponse } from '../models/register-response.model';
import { VerifyEmailRequest } from '../models/verify-email-request.model';
import { VerifyEmailResponse } from '../models/verify-email-response.model';

@Injectable({ providedIn: 'root' })
export class AuthApiService {
  private readonly httpClient = inject(HttpClient);
  private readonly baseUrl = '/api';

  login(request: LoginRequest): Observable<LoginResponse> {
    return this.httpClient.post<LoginResponse>(`${this.baseUrl}/auth/login`, request);
  }

  register(request: RegisterRequest): Observable<RegisterResponse> {
    return this.httpClient.post<RegisterResponse>(`${this.baseUrl}/auth/register`, request);
  }

  verifyEmail(request: VerifyEmailRequest): Observable<VerifyEmailResponse> {
    return this.httpClient.post<VerifyEmailResponse>(`${this.baseUrl}/auth/email/verify`, request);
  }

  authorize(params: Record<string, string>, accessToken: string): Observable<string> {
    const queryString = new URLSearchParams(params).toString();
    return new Observable<string>((subscriber) => {
      fetch(`${this.baseUrl}/oauth/authorize?${queryString}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
        redirect: 'manual',
      })
        .then((response) => {
          const location = response.headers.get('location');
          if (location) {
            subscriber.next(location);
            subscriber.complete();
          } else {
            subscriber.error(new Error('No redirect location received'));
          }
        })
        .catch((fetchError: unknown) => subscriber.error(fetchError));
    });
  }
}
