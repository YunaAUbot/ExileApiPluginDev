#nullable enable

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace ExileApiPluginDevBridge;

internal static class BridgePathResolver
{
    internal static object? Resolve(IReadOnlyDictionary<string, object?> roots, string target)
    {
        if (string.IsNullOrWhiteSpace(target))
            throw new InvalidOperationException("Target path must not be empty.");

        var root = roots.Keys.OrderByDescending(name => name.Length)
            .FirstOrDefault(name => target == name || target.StartsWith(name + ".", StringComparison.Ordinal));
        if (root == null) throw new InvalidOperationException($"Unknown DevTree shortcut: {target}");

        object? value = roots[root];
        foreach (var segment in target[root.Length..].Split('.', StringSplitOptions.RemoveEmptyEntries))
        {
            if (value == null) return null;
            if (value is IList collection && int.TryParse(segment, out var index))
            {
                if (index < 0 || index >= collection.Count)
                    throw new InvalidOperationException($"Target path index {index} is outside collection bounds in {target}");
                value = collection[index];
                continue;
            }

            var property = value.GetType().GetProperty(segment, BindingFlags.Instance | BindingFlags.Public);
            if (property == null || !property.CanRead || property.GetIndexParameters().Length != 0)
                throw new InvalidOperationException($"Target path cannot read '{segment}' in {target}");
            value = property.GetValue(value);
        }

        return value;
    }
}
