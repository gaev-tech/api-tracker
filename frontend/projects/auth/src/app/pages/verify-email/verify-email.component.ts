import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, EMPTY } from 'rxjs';
import { AuthCardComponent } from '../../components/auth-card/auth-card.component';
import { AuthApiService } from '../../services/auth-api.service';
import { ApiErrorResponse } from '../../models/api-error-response.model';

@Component({
  selector: 'app-verify-email',
  standalone: true,
  imports: [AuthCardComponent, RouterLink],
  templateUrl: './verify-email.component.html',
  styleUrl: './verify-email.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VerifyEmailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly authApiService = inject(AuthApiService);

  readonly status = signal<'loading' | 'success' | 'error'>('loading');
  readonly errorMessage = signal('');

  ngOnInit(): void {
    const verificationToken = this.extractTokenFromQuery();
    if (!verificationToken) {
      this.setErrorState('Invalid verification link.');
      return;
    }
    this.executeEmailVerification(verificationToken);
  }

  private extractTokenFromQuery(): string {
    return this.route.snapshot.queryParams['token'] ?? '';
  }

  private executeEmailVerification(verificationToken: string): void {
    this.authApiService
      .verifyEmail({ token: verificationToken })
      .pipe(
        catchError((error: unknown) => {
          this.setErrorState(this.extractErrorMessage(error));
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.handleVerificationSuccess();
      });
  }

  private handleVerificationSuccess(): void {
    this.status.set('success');
    setTimeout(() => {
      this.redirectToApplication();
    }, 2000);
  }

  private redirectToApplication(): void {
    window.location.href = '/';
  }

  private setErrorState(message: string): void {
    this.status.set('error');
    this.errorMessage.set(message);
  }

  private extractErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as ApiErrorResponse | null;
      return body?.error?.message ?? 'Verification failed';
    }
    return 'Network error. Please try again.';
  }
}
