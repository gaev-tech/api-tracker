import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { LoginRequest } from '../models/login-request.model';
import { LoginResponse } from '../models/login-response.model';
import { RegisterRequest } from '../models/register-request.model';
import { RegisterResponse } from '../models/register-response.model';
import { VerifyEmailRequest } from '../models/verify-email-request.model';
import { VerifyEmailResponse } from '../models/verify-email-response.model';

interface AuthorizeResponse {
  readonly redirect_url: string;
}

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
    const authorizationUrl = this.buildAuthorizationUrl(params);
    const headers = new HttpHeaders({
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/json',
    });
    return this.httpClient
      .get<AuthorizeResponse>(authorizationUrl, { headers })
      .pipe(map((response) => response.redirect_url));
  }

  private buildAuthorizationUrl(params: Record<string, string>): string {
    const queryString = new URLSearchParams(params).toString();
    return `${this.baseUrl}/oauth/authorize?${queryString}`;
  }
}
