import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-installation',
  standalone: true,
  templateUrl: './installation.component.html',
  styleUrls: ['./installation.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InstallationComponent {}
