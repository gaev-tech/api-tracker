import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-system-methods',
  standalone: true,
  templateUrl: './system-methods.component.html',
  styleUrls: ['./system-methods.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SystemMethodsComponent {}
