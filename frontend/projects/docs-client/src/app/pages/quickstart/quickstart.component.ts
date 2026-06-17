import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-quickstart',
  standalone: true,
  templateUrl: './quickstart.component.html',
  styleUrls: ['./quickstart.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QuickstartComponent {}
