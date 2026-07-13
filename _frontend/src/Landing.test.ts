/// <reference types="node" />

import { fireEvent } from '@testing-library/dom'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const landingHtml = readFileSync(resolve(process.cwd(), '../01_programs/app/index.html'), 'utf8')

function mountLanding(path = '/') {
  window.history.replaceState(null, '', path)
  const parsed = new DOMParser().parseFromString(landingHtml, 'text/html')
  document.head.innerHTML = parsed.head.innerHTML
  document.body.innerHTML = parsed.body.innerHTML
  const script = parsed.querySelector('script')?.textContent
  if (!script) throw new Error('landing inline behavior script is missing')
  Function(script)()
}

const nextTask = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('reviewer landing interaction', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
  })

  it('starts with only the brand and teal-dot disclosure visible', () => {
    mountLanding()
    const details = document.querySelector('details')
    const summary = document.querySelector('summary')
    const mark = document.querySelector('.mark circle')

    expect(document.querySelector('h1')).toHaveTextContent('spot')
    expect(details).not.toHaveAttribute('open')
    expect(summary).toHaveAccessibleName('Open reviewer access')
    expect(summary).toHaveAttribute('aria-expanded', 'false')
    expect(mark).toHaveAttribute('fill', '#3E7D8C')
  })

  it('presents the mark as a pressable target that never falls below 48 pixels', () => {
    mountLanding()
    const summary = document.querySelector('summary') as Element
    const mark = document.querySelector('.mark') as Element

    // The visible box tracks the wordmark's ascender band and can be smaller than the
    // target on a narrow viewport, so the hit area is sized independently by --hit,
    // whose 48px floor is the accessibility guarantee that must never regress.
    expect(getComputedStyle(summary).width).toBe('var(--hit)')
    expect(getComputedStyle(summary).cursor).toBe('pointer')
    expect(landingHtml).toContain('--hit:max(48px,var(--mark))')
    // The box must read as pressable, not decorative.
    expect(getComputedStyle(mark).borderRadius).toBe('25%')
    expect(landingHtml).toContain('summary:hover .mark')
    expect(landingHtml).toContain('summary:focus-visible .mark')
  })

  it('opens, focuses the password field, and returns focus on Escape', async () => {
    mountLanding()
    const details = document.querySelector('details') as HTMLDetailsElement
    const summary = document.querySelector('summary') as HTMLElement
    const input = document.querySelector('#access-code') as HTMLInputElement

    fireEvent.click(summary)
    await nextTask()
    expect(details.open).toBe(true)
    expect(summary).toHaveAttribute('aria-expanded', 'true')
    expect(input).toHaveFocus()

    fireEvent.keyDown(details, { key: 'Escape' })
    expect(details.open).toBe(false)
    expect(summary).toHaveFocus()
  })

  it('uses a native password POST to the exact auth route', () => {
    mountLanding()
    const form = document.querySelector('form') as HTMLFormElement
    const input = document.querySelector('#access-code') as HTMLInputElement
    const submit = document.querySelector('button[type="submit"]')

    expect(form.method).toBe('post')
    expect(new URL(form.action).pathname).toBe('/auth')
    expect(input.type).toBe('password')
    expect(input.required).toBe(true)
    expect(input.labels?.[0]).toHaveTextContent('Access code')
    expect(submit).toHaveAccessibleName('Open spot')
  })

  it('restores a compact invalid-code state without retaining the query marker', async () => {
    mountLanding('/?access=invalid')
    await nextTask()
    const details = document.querySelector('details') as HTMLDetailsElement
    const input = document.querySelector('#access-code') as HTMLInputElement

    expect(details.open).toBe(true)
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(document.querySelector('#access-status')).toHaveTextContent('Code not recognized.')
    expect(window.location.search).toBe('')
    expect(input).toHaveFocus()
  })

  it('issues no third-party request, though it may link out', () => {
    mountLanding()
    const input = document.querySelector('#access-code')
    // Anything that FETCHES must be first-party. An <a href> is a user-initiated
    // navigation and issues no request, so outbound links are permitted.
    const fetching = [...document.querySelectorAll('[src],[action]')]
      .flatMap((element) => ['src', 'action'].map((name) => element.getAttribute(name)))
      .filter((value) => /^https?:\/\//i.test(value || ''))
    const nonAnchorHref = [...document.querySelectorAll('[href]')]
      .filter((element) => element.tagName !== 'A')
      .map((element) => element.getAttribute('href'))
      .filter((value) => /^https?:\/\//i.test(value || ''))

    expect(fetching).toEqual([])
    expect(nonAnchorHref).toEqual([])
    expect(input).not.toHaveAttribute('value')
    expect(landingHtml).not.toMatch(/(?:code|password)\s*={2,3}/i)
  })

  it('toggles the access code between masked and visible without submitting', () => {
    mountLanding()
    const input = document.querySelector('#access-code') as HTMLInputElement
    const reveal = document.querySelector('#reveal-code') as HTMLButtonElement

    // Ships hidden, unhidden by script, and must never act as a submit button.
    expect(reveal.type).toBe('button')
    expect(reveal.hidden).toBe(false)
    expect(input.type).toBe('password')
    expect(reveal).toHaveAttribute('aria-pressed', 'false')
    expect(reveal).toHaveAccessibleName('Show access code')

    fireEvent.click(reveal)
    expect(input.type).toBe('text')
    expect(reveal).toHaveAttribute('aria-pressed', 'true')
    expect(reveal).toHaveAccessibleName('Hide access code')

    fireEvent.click(reveal)
    expect(input.type).toBe('password')
    expect(reveal).toHaveAttribute('aria-pressed', 'false')
  })

  it('opens an About dialog listing GitHub and contact, and closes again', () => {
    mountLanding()
    const open = document.querySelector('#about-open') as HTMLButtonElement
    const dialog = document.querySelector('#about') as HTMLDialogElement
    dialog.showModal = vi.fn(function (this: HTMLDialogElement) { this.open = true })
    dialog.close = vi.fn(function (this: HTMLDialogElement) { this.open = false })

    expect(open.type).toBe('button')
    expect(open.hidden).toBe(false)
    expect(open).toHaveAccessibleName('About spot')
    expect(dialog.open).toBe(false)

    fireEvent.click(open)
    expect(dialog.showModal).toHaveBeenCalledOnce()

    const links = [...dialog.querySelectorAll('a')].map((a) => a.getAttribute('href'))
    expect(links).toEqual([
      'https://github.com/Kirit-Singh/spot',
      'https://github.com/Kirit-Singh/spot/issues/new',
    ])
    for (const anchor of dialog.querySelectorAll('a')) {
      expect(anchor.getAttribute('rel')).toContain('noopener')
      expect(anchor.getAttribute('rel')).toContain('noreferrer')
    }

    fireEvent.click(document.querySelector('#about-close') as HTMLButtonElement)
    expect(dialog.close).toHaveBeenCalledOnce()
  })

  it('credits the author inside the About dialog, not on the landing itself', () => {
    mountLanding()
    // The root stays a bare wordmark + mark; the credit lives behind the About control.
    expect(document.querySelector('footer')).toBeNull()
    expect(document.querySelector('#about .credit')).toHaveTextContent('Kirit Singh . 2026')
    expect(document.querySelector('main')).not.toHaveTextContent('Kirit Singh')
  })
})
