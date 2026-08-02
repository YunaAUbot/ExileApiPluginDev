using System.Collections;
using Xunit;

namespace ExileApiPluginDevBridge;

public sealed class BridgePathResolverTests
{
    [Fact]
    public void Resolve_traverses_nested_collection_indexes_from_a_named_root()
    {
        var leaf = new TestNode { Text = "target" };
        var middle = new TestNode { Children = new ArrayList { leaf } };
        var root = new TestNode { Children = new ArrayList { middle } };
        var roots = new Dictionary<string, object?> { ["IngameUI"] = root };

        var result = BridgePathResolver.Resolve(roots, "IngameUI.Children.0.Children.0.Text");

        Assert.Equal("target", result);
    }

    [Fact]
    public void Resolve_rejects_an_out_of_bounds_collection_index_with_the_full_path()
    {
        var roots = new Dictionary<string, object?>
        {
            ["IngameUI"] = new TestNode { Children = new ArrayList() },
        };

        var error = Assert.Throws<InvalidOperationException>(() =>
            BridgePathResolver.Resolve(roots, "IngameUI.Children.4.Text"));

        Assert.Contains("IngameUI.Children.4.Text", error.Message);
        Assert.Contains("outside collection bounds", error.Message);
    }

    private sealed class TestNode
    {
        public IList Children { get; init; } = new ArrayList();
        public string? Text { get; init; }
    }
}
