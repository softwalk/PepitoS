import { describe, expect, it } from 'vitest';
import { ageLabel, money, ratioPct, salesLight, targetLight, ticketLight, wasteLight } from '../src/lib/format';

describe('money', () => {
  it('formatea centavos como pesos MXN', () => {
    expect(money(3500)).toBe('$35.00');
    expect(money(234000, { decimals: 0 })).toBe('$2,340');
    expect(money(-2050)).toBe('-$20.50');
    expect(money(null)).toBe('—');
  });
});

describe('semáforos PRD §15', () => {
  it('ventas/día: ≥60 verde, 45–59 ámbar, <45 rojo', () => {
    expect(salesLight(60)).toBe('green');
    expect(salesLight(75)).toBe('green');
    expect(salesLight(59)).toBe('amber');
    expect(salesLight(45)).toBe('amber');
    expect(salesLight(44)).toBe('red');
    expect(salesLight(0)).toBe('red');
  });
  it('ticket: ≥$39 verde, $36–38.99 ámbar, <$36 rojo', () => {
    expect(ticketLight(3900)).toBe('green');
    expect(ticketLight(3899)).toBe('amber');
    expect(ticketLight(3600)).toBe('amber');
    expect(ticketLight(3599)).toBe('red');
  });
  it('merma: ≤2% verde, 2–4% ámbar, >4% rojo', () => {
    expect(wasteLight(0)).toBe('green');
    expect(wasteLight(2)).toBe('green');
    expect(wasteLight(2.1)).toBe('amber');
    expect(wasteLight(4)).toBe('amber');
    expect(wasteLight(4.1)).toBe('red');
  });
  it('avance vs meta', () => {
    expect(targetLight(100)).toBe('green');
    expect(targetLight(80)).toBe('amber');
    expect(targetLight(10)).toBe('red');
  });
});

describe('helpers', () => {
  it('ratioPct y ageLabel', () => {
    expect(ratioPct(50, 200)).toBe(25);
    expect(ratioPct(5, 0)).toBe(0);
    expect(ageLabel(30)).toBe('30 min');
    expect(ageLabel(125)).toBe('2 h 5 min');
    expect(ageLabel(60 * 26)).toBe('1 d 2 h');
  });
});
