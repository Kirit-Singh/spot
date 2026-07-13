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
    expect(getComputedStyle(summary as Element).width).toBe('48px')
    expect(mark).toHaveAttribute('fill', '#3E7D8C')
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

  it('contains no external runtime resource or client-side code check', () => {
    mountLanding()
    const input = document.querySelector('#access-code')
    const external = [...document.querySelectorAll('[src],[href],[action]')]
      .flatMap((element) => ['src', 'href', 'action'].map((name) => element.getAttribute(name)))
      .filter((value) => /^https?:\/\//i.test(value || ''))

    expect(external).toEqual([])
    expect(input).not.toHaveAttribute('value')
    expect(landingHtml).not.toMatch(/(?:code|password)\s*={2,3}/i)
  })
})
