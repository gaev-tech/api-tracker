import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-rsql',
  standalone: true,
  templateUrl: './rsql.component.html',
  styleUrls: ['./rsql.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RsqlComponent {}
