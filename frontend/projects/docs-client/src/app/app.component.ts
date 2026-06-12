import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-root',
  standalone: true,
  template: '<h1>api-tracker docs — coming in M4</h1>',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent {}
