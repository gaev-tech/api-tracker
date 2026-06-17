import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-automations',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './automations.component.html',
  styleUrls: ['./automations.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AutomationsComponent {}
