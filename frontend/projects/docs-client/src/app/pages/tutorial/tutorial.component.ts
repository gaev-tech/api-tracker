import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-tutorial',
  standalone: true,
  templateUrl: './tutorial.component.html',
  styleUrls: ['./tutorial.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TutorialComponent {}
