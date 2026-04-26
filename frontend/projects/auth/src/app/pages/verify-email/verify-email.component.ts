import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, EMPTY } from 'rxjs';
import { AuthCardComponent } from '../../components/auth-card/auth-card.component';
import { AuthApiService } from '../../services/auth-api.service';
import { ApiErrorResponse } from '../../models/api-error-response.model';
import { VerificationStatus } from '../../models/verification-status.enum';
import { VERIFICATION_QUERY_PARAMS } from '../../constants/verification-query-params.constant';
import { APP_ROUTES } from '../../constants/app-routes.constant';

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
  private readonly destroyRef = inject(DestroyRef);

  readonly VerificationStatus = VerificationStatus;
  readonly status = signal<VerificationStatus>(VerificationStatus.Loading);
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
    return this.route.snapshot.queryParams[VERIFICATION_QUERY_PARAMS.TOKEN] ?? '';
  }

  private executeEmailVerification(verificationToken: string): void {
    this.authApiService
      .verifyEmail({ token: verificationToken })
      .pipe(
        catchError((error: unknown) => {
          this.setErrorState(this.extractErrorMessage(error));
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.handleVerificationSuccess();
      });
  }

  private handleVerificationSuccess(): void {
    this.status.set(VerificationStatus.Success);
    setTimeout(() => {
      this.redirectToApplication();
    }, 2000);
  }

  private redirectToApplication(): void {
    window.location.href = APP_ROUTES.HOME;
  }

  private setErrorState(message: string): void {
    this.status.set(VerificationStatus.Error);
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
