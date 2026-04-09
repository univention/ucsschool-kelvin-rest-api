# Kelvin Core Library

The core library provides a persistence-agnostic business layer for read and search access to School, User, and Group domain objects.

## Scope

- In scope:
  - read-by-identifier
  - search with filtering
  - deterministic sorting and pagination
- Out of scope in this iteration:
  - create/update/delete operations
  - Nubus synchronization flows

## Hook Policy

UDM hooks and Kelvin PyHooks are intentionally not executed in this layer.

This behavior is a design decision for the core read/search boundary and is validated by corelib tests.
