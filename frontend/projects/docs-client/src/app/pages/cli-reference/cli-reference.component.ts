import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-cli-reference',
  standalone: true,
  templateUrl: './cli-reference.component.html',
  styleUrls: ['./cli-reference.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CliReferenceComponent {}
