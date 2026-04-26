import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, EMPTY, Observable, switchMap } from 'rxjs';
import { AuthCardComponent } from '../../components/auth-card/auth-card.component';
import { AuthApiService } from '../../services/auth-api.service';
import { ApiErrorResponse } from '../../models/api-error-response.model';
import { LoginResponse } from '../../models/login-response.model';
import { OAUTH_QUERY_PARAMS } from '../../constants/oauth-query-params.constant';
import { OAUTH_DEFAULTS } from '../../constants/oauth-defaults.constant';
import { APP_ROUTES } from '../../constants/app-routes.constant';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, AuthCardComponent, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  readonly route = inject(ActivatedRoute);
  private readonly authApiService = inject(AuthApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly email = signal('');
  readonly password = signal('');
  readonly errorMessage = signal('');
  readonly isLoading = signal(false);

  private readonly clientId: string;
  private readonly redirectUri: string;
  private readonly state: string;
  private readonly codeChallenge: string;
  private readonly codeChallengeMethod: string;

  constructor() {
    const queryParams = this.route.snapshot.queryParams;
    this.clientId = queryParams[OAUTH_QUERY_PARAMS.CLIENT_ID] ?? '';
    this.redirectUri = queryParams[OAUTH_QUERY_PARAMS.REDIRECT_URI] ?? '';
    this.state = queryParams[OAUTH_QUERY_PARAMS.STATE] ?? '';
    this.codeChallenge = queryParams[OAUTH_QUERY_PARAMS.CODE_CHALLENGE] ?? '';
    this.codeChallengeMethod = queryParams[OAUTH_QUERY_PARAMS.CODE_CHALLENGE_METHOD] ?? '';
  }

  onSubmit(): void {
    this.resetState();
    this.authApiService
      .login({ email: this.email(), password: this.password() })
      .pipe(
        switchMap((loginResponse) => this.handleLoginSuccess(loginResponse)),
        catchError((error: unknown) => this.handleError(error)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((redirectUrl) => {
        this.redirectTo(redirectUrl);
      });
  }

  private resetState(): void {
    this.errorMessage.set('');
    this.isLoading.set(true);
  }

  private handleLoginSuccess(loginResponse: LoginResponse): Observable<string> {
    if (this.hasOAuthParams()) {
      const authorizeParams = this.buildAuthorizeParams();
      return this.authApiService.authorize(authorizeParams, loginResponse.access_token);
    }
    this.redirectTo(APP_ROUTES.HOME);
    return EMPTY;
  }

  private hasOAuthParams(): boolean {
    return !!(this.clientId && this.redirectUri);
  }

  private buildAuthorizeParams(): Record<string, string> {
    const params: Record<string, string> = {
      [OAUTH_QUERY_PARAMS.RESPONSE_TYPE]: OAUTH_DEFAULTS.RESPONSE_TYPE,
      [OAUTH_QUERY_PARAMS.CLIENT_ID]: this.clientId,
      [OAUTH_QUERY_PARAMS.REDIRECT_URI]: this.redirectUri,
    };
    if (this.codeChallenge) {
      params[OAUTH_QUERY_PARAMS.CODE_CHALLENGE] = this.codeChallenge;
      params[OAUTH_QUERY_PARAMS.CODE_CHALLENGE_METHOD] = this.codeChallengeMethod;
    }
    if (this.state) {
      params[OAUTH_QUERY_PARAMS.STATE] = this.state;
    }
    return params;
  }

  private handleError(error: unknown): Observable<never> {
    const message = this.extractErrorMessage(error);
    this.errorMessage.set(message);
    this.isLoading.set(false);
    return EMPTY;
  }

  private redirectTo(url: string): void {
    window.location.href = url;
  }

  private extractErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as ApiErrorResponse | null;
      return body?.error?.message ?? 'Invalid credentials';
    }
    return 'Network error. Please try again.';
  }
}
