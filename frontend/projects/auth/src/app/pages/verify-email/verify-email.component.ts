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
    const token = this.route.snapshot.queryParams['token'] ?? '';
    if (!token) {
      this.status.set('error');
      this.errorMessage.set('Invalid verification link.');
      return;
    }

    this.authApiService
      .verifyEmail({ token })
      .pipe(
        catchError((error: unknown) => {
          const message = this.extractErrorMessage(error);
          this.status.set('error');
          this.errorMessage.set(message);
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.status.set('success');
        setTimeout(() => {
          window.location.href = '/';
        }, 2000);
      });
  }

  private extractErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as ApiErrorResponse | null;
      return body?.error?.message ?? 'Verification failed';
    }
    return 'Network error. Please try again.';
  }
}
