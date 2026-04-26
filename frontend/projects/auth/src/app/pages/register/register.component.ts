import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, EMPTY, Observable } from 'rxjs';
import { AuthCardComponent } from '../../components/auth-card/auth-card.component';
import { AuthApiService } from '../../services/auth-api.service';
import { ApiErrorResponse } from '../../models/api-error-response.model';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [FormsModule, AuthCardComponent, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RegisterComponent {
  readonly route = inject(ActivatedRoute);
  private readonly authApiService = inject(AuthApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly email = signal('');
  readonly password = signal('');
  readonly errorMessage = signal('');
  readonly isLoading = signal(false);
  readonly isSuccess = signal(false);

  onSubmit(): void {
    this.resetState();
    this.authApiService
      .register({ email: this.email(), password: this.password() })
      .pipe(
        catchError((error: unknown) => this.handleRegistrationError(error)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.handleRegistrationSuccess();
      });
  }

  private resetState(): void {
    this.errorMessage.set('');
    this.isLoading.set(true);
  }

  private handleRegistrationSuccess(): void {
    this.isLoading.set(false);
    this.isSuccess.set(true);
  }

  private handleRegistrationError(error: unknown): Observable<never> {
    const message = this.extractErrorMessage(error);
    this.errorMessage.set(message);
    this.isLoading.set(false);
    return EMPTY;
  }

  private extractErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as ApiErrorResponse | null;
      return body?.error?.message ?? 'Registration failed';
    }
    return 'Network error. Please try again.';
  }
}
