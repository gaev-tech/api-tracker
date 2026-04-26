import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, EMPTY, switchMap } from 'rxjs';
import { AuthCardComponent } from '../../components/auth-card/auth-card.component';
import { AuthApiService } from '../../services/auth-api.service';
import { ApiErrorResponse } from '../../models/api-error-response.model';

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
    this.clientId = queryParams['client_id'] ?? '';
    this.redirectUri = queryParams['redirect_uri'] ?? '';
    this.state = queryParams['state'] ?? '';
    this.codeChallenge = queryParams['code_challenge'] ?? '';
    this.codeChallengeMethod = queryParams['code_challenge_method'] ?? '';
  }

  onSubmit(): void {
    this.errorMessage.set('');
    this.isLoading.set(true);

    this.authApiService
      .login({ email: this.email(), password: this.password() })
      .pipe(
        switchMap((loginResponse) => {
          if (this.clientId && this.redirectUri) {
            const authorizeParams: Record<string, string> = {
              response_type: 'code',
              client_id: this.clientId,
              redirect_uri: this.redirectUri,
            };
            if (this.codeChallenge) {
              authorizeParams['code_challenge'] = this.codeChallenge;
            }
            if (this.codeChallengeMethod) {
              authorizeParams['code_challenge_method'] = this.codeChallengeMethod;
            }
            if (this.state) {
              authorizeParams['state'] = this.state;
            }
            return this.authApiService.authorize(authorizeParams, loginResponse.access_token);
          }
          window.location.href = '/';
          return EMPTY;
        }),
        catchError((error: unknown) => {
          const message = this.extractErrorMessage(error);
          this.errorMessage.set(message);
          this.isLoading.set(false);
          return EMPTY;
        }),
      )
      .subscribe((redirectUrl) => {
        window.location.href = redirectUrl;
      });
  }

  private extractErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as ApiErrorResponse | null;
      return body?.error?.message ?? 'Invalid credentials';
    }
    return 'Network error. Please try again.';
  }
}
